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

from apps.games.cache import cached

BASE = "https://www.cheapshark.com/api/1.0"
USER_AGENT = "GamePriceTracker/0.1 (personal; polite)"

_store_cache: dict[str, str] | None = None


def _list_stores_uncached() -> dict[str, str]:
    """storeID -> storeName"""
    try:
        r = requests.get(f"{BASE}/stores", headers={"User-Agent": USER_AGENT}, timeout=10)
        r.raise_for_status()
        return {str(s["storeID"]): s["storeName"] for s in r.json() if s.get("isActive")}
    except (requests.RequestException, ValueError, KeyError):
        return {}


def list_stores() -> dict[str, str]:
    global _store_cache
    if _store_cache is None:
        _store_cache = cached("cheapshark:stores", _list_stores_uncached, timeout=86400)
    return _store_cache


def _search_games_uncached(title: str, limit: int = 5) -> list[dict[str, Any]]:
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


def search_games(title: str, limit: int = 5) -> list[dict[str, Any]]:
    title = (title or "").strip()
    if not title:
        return []
    return cached(
        f"cheapshark:search:{title.lower()}",
        lambda: _search_games_uncached(title, limit=limit),
        timeout=600,
    )


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


def _deals_by_game_id_uncached(game_id: str) -> list[dict[str, Any]]:
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
    for d in deals_raw[:20]:
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


def deals_for_title(title: str, limit: int = 20) -> list[dict[str, Any]]:
    """
    Return sorted deals across stores for a game title.
    Each: store_name, price, retail, savings, url, deal_id
    """
    title = (title or "").strip()
    if not title:
        return []
    game_id = best_match_game_id(title)
    if not game_id:
        return []
    key = f"cheapshark:deals:{game_id}"
    deals = cached(key, lambda: _deals_by_game_id_uncached(game_id), timeout=600)
    return deals[:limit]
