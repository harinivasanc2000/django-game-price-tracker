"""
Polite CeX UK client (unofficial internal API).

Base: https://wss2.cex.uk.webuy.io/v3/
Use low volume + caching. This endpoint is not officially public and may change.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

import requests

from apps.games.cache import cached

BASE = "https://wss2.cex.uk.webuy.io/v3"
USER_AGENT = "GamePriceTracker/0.1 (personal research; contact: local)"
_last_request = 0.0
MIN_INTERVAL = 1.5  # seconds between requests

SEARCH_CACHE_TTL = 1800  # 30 min — unofficial API; never hammer


def _throttle() -> None:
    global _last_request
    elapsed = time.monotonic() - _last_request
    if elapsed < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - elapsed)
    _last_request = time.monotonic()


def _search_boxes_uncached(query: str, count: int = 20) -> list[dict[str, Any]]:
    """Raw CeX request — results are cached by `search_boxes`."""
    _throttle()
    url = f"{BASE}/boxes"
    params = {
        "q": query,
        "firstRecord": 1,
        "count": min(count, 50),
        "sortBy": "relevance",
        "sortOrder": "desc",
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=12)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        return [{"_error": str(e)}]

    # Response shape varies slightly; try common paths
    boxes = (
        data.get("response", {}).get("data", {}).get("boxes")
        or data.get("data", {}).get("boxes")
        or data.get("boxes")
        or []
    )
    return boxes if isinstance(boxes, list) else []


def search_boxes(query: str, count: int = 20) -> list[dict[str, Any]]:
    """
    Search CeX boxes by keyword (cached to protect the unofficial API).
    Returns list of dicts with boxId, boxName, sellPrice, cashPrice, etc.
    """
    query = (query or "").strip()
    if not query:
        return []
    return cached(
        f"cex:boxes:{query.lower()}:{count}",
        lambda: _search_boxes_uncached(query, count=count),
        timeout=SEARCH_CACHE_TTL,
    )


def find_god_of_war_ps4() -> list[dict[str, Any]]:
    """
    Search for God of War on PS4 and return normalized price rows.
    """
    raw = search_boxes("God of War PlayStation 4", count=30)
    if raw and "_error" in raw[0]:
        return raw

    results = []
    for b in raw:
        name = (b.get("boxName") or "").lower()
        cat = (b.get("categoryName") or b.get("categoryFriendlyName") or "").lower()
        # Prefer PS4 / Playstation4 software
        if "god of war" not in name:
            continue
        if "ragnar" in name:  # skip Ragnarok unless wanted later
            continue
        if "playstation" not in cat and "ps4" not in cat and "ps4" not in name:
            # still include if name clearly PS4
            if "ps4" not in name and "playstation 4" not in name:
                continue

        sell = b.get("sellPrice")
        if sell is None:
            continue
        try:
            price = Decimal(str(sell))
        except Exception:
            continue

        results.append(
            {
                "box_id": b.get("boxId"),
                "name": b.get("boxName"),
                "price": price,
                "currency": "GBP",
                "cash_price": b.get("cashPrice"),
                "exchange_price": b.get("exchangePrice"),
                "category": b.get("categoryFriendlyName") or b.get("categoryName"),
                "in_stock": not bool(b.get("outOfStock") or b.get("outOfEcomStock")),
                "url": f"https://uk.webuy.com/product-detail/?id={b.get('boxId')}"
                if b.get("boxId")
                else "https://uk.webuy.com",
            }
        )
    return results
