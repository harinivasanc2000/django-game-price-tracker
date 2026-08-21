"""
Fetch store rows for a title + platform filter.

Order philosophy:
  1. Official digital storefront for the selected platform (PSN / Xbox / Nintendo / Steam)
  2. UK physical + local retailers (full public-search scrapes)
  3. Marketplaces

Light by design: only runs the APIs needed for the selected platform.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from decimal import Decimal
from typing import Any

from .clients.amazon_uk import search_amazon_uk
from .clients.nintendo import search_nintendo
from .clients.psn import search_psn
from .clients.uk_stores import fetch_uk_physical_bundle, platform_query, uk_search_links
from .clients.xbox import search_xbox
from .detail_helpers import empty_platform_bundle


def _ser(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        out[k] = float(v) if isinstance(v, Decimal) else v
    return out


def platform_bundle(title: str, platform: str = "") -> dict[str, Any]:
    title = (title or "").strip()
    platform = (platform or "").strip().lower()
    base = empty_platform_bundle(title, platform)
    if not title:
        return base

    # Official digital first for the chosen console family
    want_psn = platform in ("", "ps4", "ps5")
    want_xbox = platform in ("", "xbox")
    want_switch = platform in ("", "switch")
    want_physical = True  # always scrape UK locals (user asked for full local scrapes)
    want_amazon = platform in ("", "ps4", "ps5", "xbox", "switch", "pc")

    # More rows when focused on one console
    limit = 10 if platform in ("ps4", "ps5", "xbox", "switch") else 8

    psn_query = platform_query(title, platform) if platform.startswith("ps") else title
    amz_extra = platform.upper() if platform else ""

    psn_rows: list = []
    xbox_rows: list = []
    nint: dict = {"results": [], "blocked": True, "search_url": ""}
    amazon: dict = {"results": [], "blocked": True, "search_url": ""}
    uk: dict = {}

    def run_psn():
        try:
            return search_psn(psn_query, limit=limit)
        except Exception:
            return []

    def run_xbox():
        try:
            return search_xbox(title, limit=limit)
        except Exception:
            return []

    def run_nint():
        try:
            return search_nintendo(title, limit=min(limit, 8))
        except Exception:
            return {"results": [], "blocked": True, "search_url": ""}

    def run_amz():
        try:
            return search_amazon_uk(title, amz_extra, limit)
        except Exception:
            return {"results": [], "blocked": True, "search_url": ""}

    def run_uk():
        try:
            return fetch_uk_physical_bundle(title, platform, limit)
        except Exception:
            return {}

    # Store sites can be slow or deliberately challenge bots. Keep the detail
    # view useful by returning completed sources after one shared deadline.
    pool = ThreadPoolExecutor(max_workers=5)
    try:
        f_ps = pool.submit(run_psn) if want_psn else None
        f_xb = pool.submit(run_xbox) if want_xbox else None
        f_ni = pool.submit(run_nint) if want_switch else None
        f_am = pool.submit(run_amz) if want_amazon else None
        f_uk = pool.submit(run_uk) if want_physical else None
        completed, _ = wait(
            [future for future in (f_ps, f_xb, f_ni, f_am, f_uk) if future],
            timeout=10,
        )

        def result_if_done(future, fallback):
            if not future or future not in completed:
                return fallback
            try:
                return future.result() or fallback
            except Exception:
                return fallback

        psn_rows = result_if_done(f_ps, [])
        xbox_rows = result_if_done(f_xb, [])
        nint = result_if_done(f_ni, nint)
        amazon = result_if_done(f_am, amazon)
        uk = result_if_done(f_uk, {})
    finally:
        # `wait=False` is essential: a context manager would wait for an
        # unresponsive retailer after this function's ten-second deadline.
        pool.shutdown(wait=False, cancel_futures=True)

    cex = uk.get("cex") or {}
    ebay = uk.get("ebay") or {}
    game = uk.get("game") or {}
    argos = uk.get("argos") or {}
    currys = uk.get("currys") or {}
    smyths = uk.get("smyths") or {}

    base.update(
        {
            "psn_rows": [_ser(r) for r in psn_rows],
            "xbox_rows": [_ser(r) for r in xbox_rows],
            "nintendo_rows": [_ser(r) for r in (nint.get("results") or [])],
            "nintendo_blocked": bool(nint.get("blocked", True)),
            "nintendo_search_url": nint.get("search_url") or "",
            "amazon_rows": [_ser(r) for r in (amazon.get("results") or [])],
            "amazon_blocked": amazon.get("blocked", True),
            "amazon_search_url": amazon.get("search_url"),
            "cex_rows": [_ser(r) for r in (cex.get("results") or [])],
            "cex_blocked": cex.get("blocked", True),
            "cex_search_url": cex.get("search_url"),
            "ebay_rows": [_ser(r) for r in (ebay.get("results") or [])],
            "ebay_blocked": ebay.get("blocked", True),
            "ebay_search_url": ebay.get("search_url"),
            "game_rows": [_ser(r) for r in (game.get("results") or [])],
            "game_blocked": game.get("blocked", True),
            "game_search_url": game.get("search_url"),
            "argos_rows": [_ser(r) for r in (argos.get("results") or [])],
            "argos_blocked": argos.get("blocked", True),
            "argos_search_url": argos.get("search_url"),
            "currys_rows": [_ser(r) for r in (currys.get("results") or [])],
            "currys_blocked": currys.get("blocked", True),
            "currys_search_url": currys.get("search_url"),
            "smyths_rows": [_ser(r) for r in (smyths.get("results") or [])],
            "smyths_blocked": smyths.get("blocked", True),
            "smyths_search_url": smyths.get("search_url"),
            "uk_links": uk.get("uk_links") or uk_search_links(title, platform=platform),
        }
    )
    return base
