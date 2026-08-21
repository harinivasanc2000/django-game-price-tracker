"""
Parallel multi-platform search — Steam + PSN + Xbox + Nintendo.

Designed to be light:
  - short timeouts inside clients
  - Django cache on every client
  - limited result counts
  - soft-fail per platform
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Any

from .clients.nintendo import nintendo_search_url, search_nintendo
from .clients.psn import search_psn
from .clients.steam import search_store
from .clients.uk_stores import platform_query
from .clients.xbox import microsoft_store_search_url, search_xbox, xbox_search_url
from .fx import to_gbp_or_zero


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
    empty = {"steam": [], "psn": [], "xbox": [], "nintendo": [], "links": []}
    if not q:
        return empty

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

    # Fewer workers when filtered to one platform
    workers = sum([want_steam, want_psn, want_xbox, want_switch]) or 1
    with ThreadPoolExecutor(max_workers=min(workers, 4)) as pool:
        f_st = pool.submit(run_steam) if want_steam else None
        f_ps = pool.submit(run_psn) if want_psn else None
        f_xb = pool.submit(run_xbox) if want_xbox else None
        f_ni = pool.submit(run_nint) if want_switch else None
        if f_st:
            steam_rows = f_st.result() or []
        if f_ps:
            psn_rows = [_ser(r) for r in (f_ps.result() or [])]
        if f_xb:
            xbox_rows = [_ser(r) for r in (f_xb.result() or [])]
        if f_ni:
            nint_block = f_ni.result() or nint_block

    nint_rows = [_ser(r) for r in (nint_block.get("results") or [])]

    links = [
        {"name": "Steam", "platform": "pc", "url": f"https://store.steampowered.com/search/?term={q}"},
        {"name": "PlayStation Store", "platform": "ps5", "url": f"https://store.playstation.com/en-gb/search/{q}"},
        {"name": "Xbox", "platform": "xbox", "url": xbox_search_url(q)},
        {"name": "Microsoft Store", "platform": "xbox", "url": microsoft_store_search_url(q)},
        {"name": "Nintendo eShop UK", "platform": "switch", "url": nint_block.get("search_url") or nintendo_search_url(q)},
    ]

    return {
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
