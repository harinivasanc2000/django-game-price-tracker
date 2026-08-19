"""
CheapShark public API (no key) — multi-store PC digital prices.

https://www.cheapshark.com/api/1.0/
Stores include Steam, GOG, Humble, Fanatical, GreenManGaming, Epic, etc.
Prices are typically USD; we label currency as USD from the API.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import requests

BASE = "https://www.cheapshark.com/api/1.0"
USER_AGENT = "GamePriceTracker/0.1 (personal; polite)"

_store_cache: dict[str, str] | None = None


def list_stores() -> dict[str, str]:
    """storeID -> storeName"""
    global _store_cache
    if _store_cache is not None:
        return _store_cache
    try:
        r = requests.get(f"{BASE}/stores", headers={"User-Agent": USER_AGENT}, timeout=10)
        r.raise_for_status()
        _store_cache = {str(s["storeID"]): s["storeName"] for s in r.json() if s.get("isActive")}
    except (requests.RequestException, ValueError, KeyError):
        _store_cache = {}
    return _store_cache


def search_games(title: str, limit: int = 5) -> list[dict[str, Any]]:
    title = (title or "").strip()
    if not title:
        return []
    try:
        r = requests.get(
            f"{BASE}/games",
            params={"title": title, "limit": limit},
            headers={"User-Agent": USER_AGENT},
            timeout=12,
        )
        r.raise_for_status()
        return r.json() or []
    except (requests.RequestException, ValueError):
        return []


def best_match_game_id(title: str) -> str | None:
    results = search_games(title, limit=8)
    if not results:
        return None
    t = title.lower()
    for g in results:
        if (g.get("external") or "").lower() == t:
            return str(g["gameID"])
    for g in results:
        if t in (g.get("external") or "").lower():
            return str(g["gameID"])
    return str(results[0]["gameID"])


def deals_for_title(title: str, limit: int = 20) -> list[dict[str, Any]]:
    """
    Return sorted deals across stores for a game title.
    Each: store_name, price, retail, savings, url, deal_id
    """
    game_id = best_match_game_id(title)
    if not game_id:
        return []

    stores = list_stores()
    try:
        r = requests.get(
            f"{BASE}/games",
            params={"id": game_id},
            headers={"User-Agent": USER_AGENT},
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError):
        return []

    deals_raw = data.get("deals") or []
    out = []
    for d in deals_raw[:limit]:
        sid = str(d.get("storeID", ""))
        price = Decimal(str(d.get("price", "0")))
        retail = Decimal(str(d.get("retailPrice", "0")))
        savings = float(d.get("savings") or 0)
        deal_id = d.get("dealID") or ""
        out.append(
            {
                "store_name": stores.get(sid, f"Store {sid}"),
                "store_id": sid,
                "price": price,
                "retail": retail,
                "savings": int(round(savings)),
                "currency": "USD",
                "url": f"https://www.cheapshark.com/redirect?dealID={deal_id}" if deal_id else "",
            }
        )
    out.sort(key=lambda x: x["price"])
    return out
