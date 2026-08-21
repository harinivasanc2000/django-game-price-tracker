"""Helpers for game detail page resilience + related titles."""
from __future__ import annotations

from typing import Any

from .clients.steam import search_store
from .clients.uk_stores import uk_search_links


def empty_platform_bundle(title: str = "", platform: str = "") -> dict[str, Any]:
    return {
        "platform": platform or "",
        "psn_rows": [],
        "xbox_rows": [],
        "nintendo_rows": [],
        "nintendo_blocked": True,
        "nintendo_search_url": "",
        "amazon_rows": [],
        "amazon_blocked": True,
        "amazon_search_url": "",
        "cex_rows": [],
        "cex_blocked": True,
        "cex_search_url": "",
        "ebay_rows": [],
        "ebay_blocked": True,
        "ebay_search_url": "",
        "game_rows": [],
        "game_blocked": True,
        "game_search_url": "",
        "argos_rows": [],
        "argos_blocked": True,
        "argos_search_url": "",
        "currys_rows": [],
        "currys_blocked": True,
        "currys_search_url": "",
        "uk_links": uk_search_links(title, platform=platform) if title else [],
    }


def similar_steam_titles(
    name: str, app_id: int, country: str = "GB", limit: int = 6
) -> list[dict[str, Any]]:
    """Related / edition search via public Steam storesearch."""
    name = (name or "").strip()
    if len(name) < 3:
        return []
    parts = [p for p in name.replace(":", " ").split() if len(p) > 1][:3]
    q = " ".join(parts) if parts else name
    try:
        rows = search_store(q, country=country, limit=12)
    except Exception:
        return []
    out = []
    for r in rows:
        if r.get("app_id") == app_id:
            continue
        if r.get("is_likely_dlc"):
            continue
        out.append(
            {
                "app_id": r["app_id"],
                "name": r["name"],
                "tiny_image": r.get("tiny_image") or "",
                "price": r.get("price"),
                "currency": r.get("currency") or "GBP",
                "price_status": r.get("price_status"),
                "discount": r.get("discount") or 0,
            }
        )
        if len(out) >= limit:
            break
    return out
