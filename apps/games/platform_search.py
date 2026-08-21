"""
Parallel multi-platform search — Steam + PSN + Xbox + Nintendo.

Designed to be light:
  - short timeouts inside clients
  - Django cache on every client + top-level result cache
  - limited result counts
  - soft-fail per platform
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from typing import Any

from django.core.cache import cache

from .clients.nintendo import nintendo_search_url, search_nintendo
from .clients.psn import search_psn
from .clients.steam import search_store
from .clients.uk_stores import platform_query
from .clients.xbox import microsoft_store_search_url, search_xbox, xbox_search_url
from .fx import to_gbp_or_zero

MPS_TTL = 180  # whole multi-platform search cache


def _ser(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        out[k] = float(v) if isinstance(v, Decimal) else v
    return out


def multi_platform_search(
    query: str,
    *,
    platform: str = "",
    country: str = "GB",
    limit: int = 8,
) -> dict[str, Any]:
    """
    Returns buckets:
      steam, psn, xbox, nintendo, links
    Only runs the platforms needed for `platform` filter (saves RAM/CPU).
    """
    q = (query or "").strip()
    plat = (platform or "").strip().lower()
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

    cache_key = f"mps:v2:{q.lower()}:{plat}:{country}:{limit}"
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    want_steam = plat in ("", "pc")
    want_psn = plat in ("", "ps4", "ps5")
    want_xbox = plat in ("", "xbox")
    want_switch = plat in ("", "switch")

    steam_q = platform_query(q, plat) if plat else q
    psn_q = platform_query(q, plat) if plat.startswith("ps") else q

    steam_rows: list = []
    psn_rows: list = []
    xbox_rows: list = []
    nint_block: dict = {"results": [], "blocked": True, "search_url": nintendo_search_url(q)}

    def run_steam():
        try:
            return search_store(steam_q, country=country, limit=limit)
        except Exception:
            return []

    def run_psn():
        try:
            return search_psn(psn_q, limit=limit)
        except Exception:
            return []

    def run_xbox():
        try:
            return search_xbox(q, limit=limit)
        except Exception:
            return []

    def run_nint():
        try:
            return search_nintendo(q, limit=min(limit, 6))
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
            for fut in as_completed(futures, timeout=8):
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
            # Do not use a context manager here: its implicit wait would undo
            # this timeout by waiting for slow network workers on exit.
            pass
    finally:
        # Running requests may finish and warm their own caches, but they must
        # never hold this web request open after the eight-second budget.
        pool.shutdown(wait=False, cancel_futures=True)

    nint_rows = [_ser(r) for r in (nint_block.get("results") or [])]

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
        "nintendo_blocked": bool(nint_block.get("blocked")),
        "nintendo_search_url": nint_block.get("search_url") or nintendo_search_url(q),
        "links": links,
        "query": q,
        "platform": plat,
    }
    cache.set(cache_key, payload, MPS_TTL)
    return payload


def cheapest_hint(buckets: dict[str, Any]) -> dict[str, Any] | None:
    """Best GBP-ish hint across platform buckets for UI strip."""
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
