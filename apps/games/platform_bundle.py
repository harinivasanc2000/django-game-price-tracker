"""
Fetch store rows for a title + platform / price / condition filters.

Order philosophy:
  1. Official digital storefront for the selected platform
  2. UK physical + local retailers (public-search scrapes)
  3. Marketplaces

Cached ~3 minutes so filtered navigation and reloads stay cheap.
"""

from __future__ import annotations

import hashlib
import math
from concurrent.futures import wait
from decimal import Decimal
from typing import Any

from .cache import cached
from .clients.amazon_uk import search_amazon_uk
from .clients.nintendo import search_nintendo
from .clients.psn import search_psn
from .clients.scrape_filters import parse_price_bound
from .clients.uk_stores import fetch_uk_physical_bundle, platform_query, uk_search_links
from .clients.xbox import search_xbox
from .detail_helpers import empty_platform_bundle
from .constants import STORE_PLATFORMS
from .executors import BUNDLE_EXECUTOR, cancel_pending

BUNDLE_TTL = 180
BUNDLE_TIMEOUT = 9.0
_PLATFORM_VALUES = frozenset({"", *(value for value, _label in STORE_PLATFORMS)})
_CONDITION_VALUES = frozenset({"", "new", "used"})


def _bundle_cache_key(
    title: str, platform: str, min_price: str, max_price: str, condition: str
) -> str:
    """Return a short backend-safe identity for user/catalogue text."""
    identity = "|".join(
        (title.casefold(), platform, min_price, max_price, condition)
    )
    digest = hashlib.blake2s(identity.encode("utf-8"), digest_size=12).hexdigest()
    return f"pb:v3:{digest}"


def _ser(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        out[k] = float(v) if isinstance(v, Decimal) else v
    return out


def _platform_bundle_impl(
    title: str,
    platform: str = "",
    *,
    min_price: Decimal | str | None = None,
    max_price: Decimal | str | None = None,
    condition: str = "",
) -> dict[str, Any]:
    title = (title or "").strip()[:160]
    platform = (platform or "").strip().lower()
    if platform not in _PLATFORM_VALUES:
        platform = ""
    lo = parse_price_bound(str(min_price) if min_price is not None else None)
    hi = parse_price_bound(str(max_price) if max_price is not None else None)
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    cond = (condition or "").strip().lower()
    if cond not in _CONDITION_VALUES:
        cond = ""

    base = empty_platform_bundle(title, platform)
    if not title:
        return base

    lo_s = str(lo) if lo is not None else ""
    hi_s = str(hi) if hi is not None else ""
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

    futures = {BUNDLE_EXECUTOR.submit(fn): name for name, fn in jobs}
    completed, _ = wait(futures.keys(), timeout=BUNDLE_TIMEOUT)
    cancel_pending(futures)
    base["_cache_incomplete"] = len(completed) < len(futures)

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

    def price_ok(row: dict) -> bool:
        raw_price = row.get("price")
        has_price_band = lo is not None or hi is not None
        if raw_price in (None, ""):
            return not has_price_band
        try:
            p = float(raw_price)
        except (TypeError, ValueError, OverflowError):
            return False
        if not math.isfinite(p) or p < 0:
            return False
        if lo is not None and p < float(lo):
            return False
        if hi is not None and p > float(hi):
            return False
        return True

    psn_rows = [r for r in psn_rows if price_ok(r)]
    xbox_rows = [r for r in xbox_rows if price_ok(r)]
    nint_results = [r for r in (nint.get("results") or []) if price_ok(r)]

    def filtered_rows(source: dict) -> list[dict]:
        """Defend the bundle contract even when an individual client misses a filter."""
        return [row for row in (source.get("results") or []) if price_ok(row)]

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
                "rows": [_ser(row) for row in filtered_rows(source)],
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
            "amazon_rows": [_ser(r) for r in filtered_rows(amazon)],
            "amazon_blocked": amazon.get("blocked", True),
            "amazon_search_url": amazon.get("search_url"),
            "cex_rows": [_ser(r) for r in filtered_rows(cex)],
            "cex_blocked": cex.get("blocked", True),
            "cex_search_url": cex.get("search_url"),
            "ebay_rows": [_ser(r) for r in filtered_rows(ebay)],
            "ebay_blocked": ebay.get("blocked", True),
            "ebay_search_url": ebay.get("search_url"),
            "game_rows": [_ser(r) for r in filtered_rows(game)],
            "game_blocked": game.get("blocked", True),
            "game_search_url": game.get("search_url"),
            "argos_rows": [_ser(r) for r in filtered_rows(argos)],
            "argos_blocked": argos.get("blocked", True),
            "argos_search_url": argos.get("search_url"),
            "currys_rows": [_ser(r) for r in filtered_rows(currys)],
            "currys_blocked": currys.get("blocked", True),
            "currys_search_url": currys.get("search_url"),
            "smyths_rows": [_ser(r) for r in filtered_rows(smyths)],
            "smyths_blocked": smyths.get("blocked", True),
            "smyths_search_url": smyths.get("search_url"),
            "musicmagpie_rows": [_ser(r) for r in filtered_rows(mm)],
            "musicmagpie_blocked": mm.get("blocked", True),
            "musicmagpie_search_url": mm.get("search_url"),
            "specialist_sources": specialist_sources,
            "best_local": [
                _ser(r)
                for r in (uk.get("best_local") or [])
                if r.get("in_stock") is not False and price_ok(r)
            ],
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
    return base


def platform_bundle(
    title: str,
    platform: str = "",
    *,
    min_price: Decimal | str | None = None,
    max_price: Decimal | str | None = None,
    condition: str = "",
) -> dict[str, Any]:
    """Collapse concurrent identical bundle misses into one network fan-out."""
    clean_title = (title or "").strip()[:160]
    clean_platform = (platform or "").strip().lower()
    if clean_platform not in _PLATFORM_VALUES:
        clean_platform = ""
    lo = parse_price_bound(str(min_price) if min_price is not None else None)
    hi = parse_price_bound(str(max_price) if max_price is not None else None)
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    clean_condition = (condition or "").strip().lower()
    if clean_condition not in _CONDITION_VALUES:
        clean_condition = ""
    key = _bundle_cache_key(
        clean_title,
        clean_platform,
        str(lo) if lo is not None else "",
        str(hi) if hi is not None else "",
        clean_condition,
    )
    return cached(
        key,
        lambda: _platform_bundle_impl(
            clean_title,
            clean_platform,
            min_price=lo,
            max_price=hi,
            condition=clean_condition,
        ),
        BUNDLE_TTL,
        empty_timeout=15,
    )
