"""
Parallel multi-platform search — Steam + PSN + Xbox + Nintendo.

Light by design:
  - short client timeouts + hard 6s pool deadline
  - Django cache on clients + top-level MPS cache
  - capped result counts (no over-fetch beyond 1.5×)
  - soft-fail per platform
  - strict title_match to kill franchise bleed
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from typing import Any

from django.core.cache import cache

from .clients.nintendo import nintendo_search_url, search_nintendo
from .clients.psn import search_psn
from .clients.steam import search_store
from .clients.title_match import filter_by_title
from .clients.uk_stores import platform_query
from .clients.xbox import microsoft_store_search_url, search_xbox, xbox_search_url
from .fx import to_gbp_or_zero

MPS_TTL = 240  # 4 min — search is hot path
POOL_TIMEOUT = 6.0


def _ser(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, Decimal):
            out[k] = float(v)
        else:
            out[k] = v
    return out


def _price_filter_rows(
    rows: list[dict],
    *,
    min_price: float | None = None,
    max_price: float | None = None,
    hide_free: bool = False,
) -> list[dict]:
    if min_price is None and max_price is None and not hide_free:
        return rows
    out = []
    for r in rows:
        status = r.get("price_status")
        has = r.get("has_price")
        try:
            p = float(r["price"]) if r.get("price") is not None else None
        except (TypeError, ValueError):
            p = None
        if hide_free and (status == "free" or (p is not None and p <= 0 and status != "unknown")):
            continue
        if p is not None and p > 0:
            if min_price is not None and p < min_price:
                continue
            if max_price is not None and p > max_price:
                continue
        elif min_price is not None or max_price is not None:
            # unknown price: keep only if no hard band required for paid items
            if has is False or status in ("unknown", None):
                if min_price is not None:
                    continue
        out.append(r)
    return out


def multi_platform_search(
    query: str,
    *,
    platform: str = "",
    country: str = "GB",
    limit: int = 8,
    min_price: float | None = None,
    max_price: float | None = None,
    hide_dlc: bool = False,
    hide_free: bool = False,
) -> dict[str, Any]:
    q = (query or "").strip()[:120]
    plat = (platform or "").strip().lower()
    limit = max(4, min(int(limit or 8), 16))

    empty = {
        "steam": [],
        "psn": [],
        "xbox": [],
        "nintendo": [],
        "links": [],
        "nintendo_blocked": True,
        "nintendo_search_url": nintendo_search_url(q) if q else "",
        "query": q,
        "platform": plat,
    }
    if not q:
        return empty

    # Include filter dims in key so filtered views cache separately
    lo = f"{min_price:.2f}" if min_price is not None else ""
    hi = f"{max_price:.2f}" if max_price is not None else ""
    cache_key = f"mps:v5:{q.lower()}:{plat}:{country}:{limit}:{lo}:{hi}:{int(hide_dlc)}:{int(hide_free)}"
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    want_steam = plat in ("", "pc")
    want_psn = plat in ("", "ps4", "ps5")
    want_xbox = plat in ("", "xbox")
    want_switch = plat in ("", "switch")

    steam_q = platform_query(q, plat) if plat else q
    psn_q = platform_query(q, plat) if plat.startswith("ps") else q
    fetch_n = max(limit + 4, 10)  # modest over-fetch for title_match

    steam_rows: list = []
    psn_rows: list = []
    xbox_rows: list = []
    nint_block: dict = {"results": [], "blocked": True, "search_url": nintendo_search_url(q)}

    def run_steam():
        try:
            return search_store(steam_q, country=country, limit=fetch_n)
        except Exception:
            return []

    def run_psn():
        try:
            return search_psn(psn_q, limit=fetch_n)
        except Exception:
            return []

    def run_xbox():
        try:
            return search_xbox(q, limit=fetch_n)
        except Exception:
            return []

    def run_nint():
        try:
            return search_nintendo(q, limit=min(fetch_n, 10))
        except Exception:
            return {"results": [], "blocked": True, "search_url": nintendo_search_url(q)}

    workers = sum([want_steam, want_psn, want_xbox, want_switch]) or 1
    futures = {}
    pool = ThreadPoolExecutor(max_workers=min(workers, 4))
    try:
        if want_steam:
            futures[pool.submit(run_steam)] = "steam"
        if want_psn:
            futures[pool.submit(run_psn)] = "psn"
        if want_xbox:
            futures[pool.submit(run_xbox)] = "xbox"
        if want_switch:
            futures[pool.submit(run_nint)] = "nint"

        try:
            for fut in as_completed(futures, timeout=POOL_TIMEOUT):
                kind = futures[fut]
                try:
                    result = fut.result()
                except Exception:
                    continue
                if kind == "steam":
                    steam_rows = result or []
                elif kind == "psn":
                    psn_rows = [_ser(r) for r in (result or [])]
                elif kind == "xbox":
                    xbox_rows = [_ser(r) for r in (result or [])]
                elif kind == "nint":
                    nint_block = result or nint_block
        except TimeoutError:
            pass
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    steam_rows = filter_by_title(steam_rows, q, min_score=0.67)
    if hide_dlc:
        steam_rows = [r for r in steam_rows if not r.get("is_likely_dlc")]
    steam_rows = _price_filter_rows(
        steam_rows, min_price=min_price, max_price=max_price, hide_free=hide_free
    )[:limit]

    psn_rows = filter_by_title(psn_rows, q, min_score=0.67)
    psn_rows = _price_filter_rows(
        psn_rows, min_price=min_price, max_price=max_price, hide_free=hide_free
    )[:limit]

    xbox_rows = filter_by_title(xbox_rows, q, min_score=0.67)
    xbox_rows = _price_filter_rows(
        xbox_rows, min_price=min_price, max_price=max_price, hide_free=hide_free
    )[:limit]

    nint_rows = filter_by_title(
        [_ser(r) for r in (nint_block.get("results") or [])], q, min_score=0.67
    )
    nint_rows = _price_filter_rows(
        nint_rows, min_price=min_price, max_price=max_price, hide_free=hide_free
    )[:limit]

    links = [
        {"name": "Steam", "platform": "pc", "url": f"https://store.steampowered.com/search/?term={q}"},
        {
            "name": "PlayStation Store",
            "platform": "ps5",
            "url": f"https://store.playstation.com/en-gb/search/{q}",
        },
        {"name": "Xbox", "platform": "xbox", "url": xbox_search_url(q)},
        {"name": "Microsoft Store", "platform": "xbox", "url": microsoft_store_search_url(q)},
        {
            "name": "Nintendo eShop UK",
            "platform": "switch",
            "url": nint_block.get("search_url") or nintendo_search_url(q),
        },
    ]

    payload = {
        "steam": steam_rows,
        "psn": psn_rows,
        "xbox": xbox_rows,
        "nintendo": nint_rows,
        "nintendo_blocked": bool(nint_block.get("blocked")) and not nint_rows,
        "nintendo_search_url": nint_block.get("search_url") or nintendo_search_url(q),
        "links": links,
        "query": q,
        "platform": plat,
    }
    cache.set(cache_key, payload, MPS_TTL)
    return payload


def cheapest_hint(buckets: dict[str, Any]) -> dict[str, Any] | None:
    candidates = []
    for r in buckets.get("steam") or []:
        if r.get("price_status") == "paid" and r.get("price") is not None:
            candidates.append(
                {
                    "platform": "PC / Steam",
                    "title": r.get("name"),
                    "price_gbp": float(to_gbp_or_zero(r["price"], r.get("currency") or "GBP")),
                    "url": f"/steam/{r.get('app_id')}/" if r.get("app_id") else r.get("url"),
                }
            )
    for r in buckets.get("psn") or []:
        if float(r.get("price") or 0) > 0:
            candidates.append(
                {
                    "platform": "PlayStation",
                    "title": r.get("name"),
                    "price_gbp": float(r["price"]),
                    "url": r.get("url"),
                }
            )
    for r in buckets.get("xbox") or []:
        if r.get("has_price") and float(r.get("price") or 0) > 0:
            candidates.append(
                {
                    "platform": "Xbox",
                    "title": r.get("name"),
                    "price_gbp": float(to_gbp_or_zero(r["price"], r.get("currency") or "GBP")),
                    "url": r.get("url"),
                }
            )
    for r in buckets.get("nintendo") or []:
        if r.get("has_price") and float(r.get("price") or 0) > 0:
            candidates.append(
                {
                    "platform": "Switch",
                    "title": r.get("name"),
                    "price_gbp": float(r["price"]),
                    "url": r.get("url"),
                }
            )
    if not candidates:
        return None
    candidates.sort(key=lambda x: x["price_gbp"])
    return candidates[0]
