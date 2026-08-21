"""
Post-scrape filters for public product search results.

All stores here are searchable without login. Filters never require accounts.
Applied after BeautifulSoup extraction so blocked sites still keep search_url.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

# Words that usually mean "not a full game disc/cart"
_ACCESSORY = (
    "controller", "dualsense", "dualshock", "gamepad", "headset", "earbud",
    "carry case", "travel case", "charging dock", "charge station", "thumb grip",
    "silicone", "skin cover", "screen protector", "stand only", "mount only",
    "microfibre", "cleaning kit", "battery pack", "power bank", "charger only",
)

_PLATFORM_TOKENS = {
    "ps4": ("ps4", "playstation 4", "play station 4"),
    "ps5": ("ps5", "playstation 5", "play station 5"),
    "xbox": ("xbox", "series x", "series s", "xbox one"),
    "switch": ("switch", "nintendo switch"),
    "pc": ("pc", "steam", "windows"),
}

_USED_HINTS = (
    "used", "pre-owned", "preowned", "pre owned", "second hand", "secondhand",
    "refurbished", "refurb", "cex", "graded",
)
_NEW_HINTS = ("brand new", "brand-new", "sealed", "factory sealed", "new only")


def parse_price_bound(raw: str | None) -> Decimal | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        v = Decimal(str(raw).strip().replace("£", "").replace(",", ""))
        return v if v >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def detect_condition(name: str, is_used_flag: bool | None = None) -> str:
    """Return 'used' | 'new' | 'unknown'."""
    n = (name or "").lower()
    if is_used_flag is True:
        return "used"
    if any(h in n for h in _USED_HINTS):
        return "used"
    if any(h in n for h in _NEW_HINTS):
        return "new"
    if is_used_flag is False:
        return "new"
    return "unknown"


def platform_hint_in_name(name: str, platform: str) -> bool:
    """If a platform filter is set, prefer listings that mention it (soft)."""
    plat = (platform or "").strip().lower()
    if not plat or plat not in _PLATFORM_TOKENS:
        return True
    n = (name or "").lower()
    tokens = _PLATFORM_TOKENS[plat]
    # Soft: if no platform words at all in the name, still keep (many titles omit it)
    any_plat = any(
        t in n
        for group in _PLATFORM_TOKENS.values()
        for t in group
    )
    if not any_plat:
        return True
    return any(t in n for t in tokens)


def is_accessory(name: str) -> bool:
    return any(h in (name or "").lower() for h in _ACCESSORY)


def filter_product_rows(
    rows: list[dict[str, Any]] | None,
    *,
    title: str = "",
    platform: str = "",
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    condition: str = "",
    exclude_accessories: bool = True,
) -> list[dict[str, Any]]:
    """
    Filter scraped product rows in-memory.

    condition: '' | 'any' | 'new' | 'used'
    """
    out: list[dict[str, Any]] = []
    cond = (condition or "").strip().lower()
    if cond in ("any", "all"):
        cond = ""

    for row in rows or []:
        name = row.get("name") or ""
        if exclude_accessories and is_accessory(name):
            # Keep only if title tokens strongly present (bundle cases)
            if title:
                tokens = [
                    t
                    for t in re.findall(r"[a-z0-9]+", title.lower())
                    if len(t) > 2
                ][:4]
                hits = sum(1 for t in tokens if t in name.lower())
                if hits < min(2, len(tokens) or 1):
                    continue
            else:
                continue

        price = row.get("price")
        try:
            p = float(price) if price is not None else None
        except (TypeError, ValueError):
            p = None
        if p is not None:
            if min_price is not None and p < float(min_price):
                continue
            if max_price is not None and p > float(max_price):
                continue

        if not platform_hint_in_name(name, platform):
            continue

        row_cond = detect_condition(name, row.get("is_used"))
        row = dict(row)
        row["condition"] = row_cond
        if cond in ("new", "used") and row_cond not in (cond, "unknown"):
            # Drop definite mismatches; keep unknown
            if row_cond != cond:
                continue

        out.append(row)

    out.sort(
        key=lambda r: float(r["price"]) if r.get("price") is not None else 999999.0
    )
    return out


def filter_source_dict(
    source: dict[str, Any] | None,
    *,
    title: str = "",
    platform: str = "",
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    condition: str = "",
) -> dict[str, Any]:
    source = dict(source or {})
    rows = filter_product_rows(
        source.get("results") or [],
        title=title,
        platform=platform,
        min_price=min_price,
        max_price=max_price,
        condition=condition,
    )
    source["results"] = rows
    if not rows:
        source["blocked"] = True
    return source
