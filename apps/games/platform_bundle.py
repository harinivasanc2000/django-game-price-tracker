"""
Fetch store rows for a title + platform / price / condition filters.

Order philosophy:
  1. Official digital storefront for the selected platform
  2. UK physical + local retailers (public-search scrapes)
  3. Marketplaces

Cached ~3 minutes so AJAX platform switches and reloads stay cheap.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from decimal import Decimal
from typing import Any

from django.core.cache import cache

from .clients.amazon_uk import search_amazon_uk
from .clients.nintendo import search_nintendo
from .clients.psn import search_psn
from .clients.scrape_filters import parse_price_bound
from .clients.uk_stores import fetch_uk_physical_bundle, platform_query, uk_search_links
from .clients.xbox import search_xbox
from .detail_helpers import empty_platform_bundle

BUNDLE_TTL = 180
BUNDLE_TIMEOUT = 9.0


def _ser(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        out[k] = float(v) if isinstance(v, Decimal) else v
    return out


def platform_bundle(
    title: str,
    platform: str = "",
    *,
    min_price: Decimal | str | None = None,
    max_price: Decimal | str | None = None,
    condition: str = "",
) -> dict[str, Any]:
    title = (title or "").strip()[:160]
    platform = (platform or "").strip().lower()
    lo = parse_price_bound(str(min_price) if min_price is not None else None)
    hi = parse_price_bound(str(max_price) if max_price is not None else None)
    cond = (condition or "").strip().lower()

    base = empty_platform_bundle(title, platform)
    if not title:
        return base

    lo_s = str(lo) if lo is not None else ""
    hi_s = str(hi) if hi is not None else ""
    cache_key = f"pb:v2:{title.lower()}:{platform}:{lo_s}:{hi_s}:{cond}"
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    want_psn = platform in ("", "ps4", "ps5")
    want_xbox = platform in ("", "xbox")
    want_switch = platform in ("", "switch")
    want_physical = True
    # Amazon rarely lists "used" discs usefully for games — skip when filtering used only
    want_amazon = platform in ("", "ps4", "ps5", "xbox", "switch", "pc") and cond != "used"

    limit = 8 if platform in ("ps4", "ps5", "xbox", "switch") else 6

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
            return search_nintendo(title, limit=min(limit, 6))
        except Exception:
            return {"results": [], "blocked": True, "search_url": ""}

    def run_amz():
        try:
            return search_amazon_uk(
                title,
                amz_extra,
                limit,
                platform=platform,
                min_price=lo,
                max_price=hi,
                condition=cond,
            )
        except Exception:
            return {"results": [], "blocked": True, "search_url": ""}

    def run_uk():
        try:
            return fetch_uk_physical_bundle(
                title,
                platform,
                limit,
                min_price=lo,
                max_price=hi,
                condition=cond,
            )
        except Exception:
            return {}

    jobs = []
    if want_psn:
        jobs.append(("psn", run_psn))
    if want_xbox:
        jobs.append(("xbox", run_xbox))
    if want_switch:
        jobs.append(("nint", run_nint))
    if want_amazon:
        jobs.append(("amz", run_amz))
    if want_physical:
        jobs.append(("uk", run_uk))

    pool = ThreadPoolExecutor(max_workers=min(len(jobs) or 1, 5))
    try:
        futures = {pool.submit(fn): name for name, fn in jobs}
        completed, _ = wait(futures.keys(), timeout=BUNDLE_TIMEOUT)

        for fut in completed:
            name = futures[fut]
            try:
                result = fut.result()
            except Exception:
                continue
            if name == "psn":
                psn_rows = result or []
            elif name == "xbox":
                xbox_rows = result or []
            elif name == "nint":
                nint = result or nint
            elif name == "amz":
                amazon = result or amazon
            elif name == "uk":
                uk = result or {}
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    def price_ok(row: dict) -> bool:
        try:
            p = float(row.get("price") or 0)
        except (TypeError, ValueError):
            return True
        if p <= 0:
            return True
        if lo is not None and p < float(lo):
            return False
        if hi is not None and p > float(hi):
            return False
        return True

    psn_rows = [r for r in psn_rows if price_ok(r)]
    xbox_rows = [r for r in xbox_rows if price_ok(r)]
    nint_results = [r for r in (nint.get("results") or []) if price_ok(r)]

    cex = uk.get("cex") or {}
    ebay = uk.get("ebay") or {}
    game = uk.get("game") or {}
    argos = uk.get("argos") or {}
    currys = uk.get("currys") or {}
    smyths = uk.get("smyths") or {}
    mm = uk.get("musicmagpie") or {}
    # These stores share a generic BS4 contract, so carry them as structured
    # sources rather than adding four more near-identical template branches.
    specialist_sources = []
    for key, label in (
        ("the_game_collection", "The Game Collection"),
        ("hit", "Hit"),
        ("shopto", "ShopTo"),
        ("simplygames", "SimplyGames"),
    ):
        source = uk.get(key) or {}
        specialist_sources.append(
            {
                "key": key,
                "label": label,
                "rows": [_ser(row) for row in (source.get("results") or [])],
                "blocked": source.get("blocked", True),
                "search_url": source.get("search_url") or "",
            }
        )

    base.update(
        {
            "psn_rows": [_ser(r) for r in psn_rows],
            "xbox_rows": [_ser(r) for r in xbox_rows],
            "nintendo_rows": [_ser(r) for r in nint_results],
            "nintendo_blocked": bool(nint.get("blocked", True)) or not nint_results,
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
            "musicmagpie_rows": [_ser(r) for r in (mm.get("results") or [])],
            "musicmagpie_blocked": mm.get("blocked", True),
            "musicmagpie_search_url": mm.get("search_url"),
            "specialist_sources": specialist_sources,
            "best_local": [_ser(r) for r in (uk.get("best_local") or [])],
            "stores_ok": uk.get("stores_ok") or 0,
            "stores_total": uk.get("stores_total") or 11,
            "uk_links": uk.get("uk_links")
            or uk_search_links(title, platform, min_price=lo, max_price=hi, condition=cond),
            "active_filters": {
                "platform": platform,
                "min_price": lo_s,
                "max_price": hi_s,
                "condition": cond,
            },
        }
    )
    cache.set(cache_key, base, BUNDLE_TTL)
    return base
