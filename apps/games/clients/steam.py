"""
Steam Store public API client (no key required for basic prices).

Endpoint:
  GET https://store.steampowered.com/api/appdetails?appids={id}&cc={country}&filters=price_overview

Rate limit: ~200 requests / 5 minutes. Be polite.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import requests

STORE_API = "https://store.steampowered.com/api/appdetails"
USER_AGENT = "GamePriceTracker/0.1 (personal; polite)"

# God of War (2018) on Steam
GOD_OF_WAR_STEAM_APP_ID = 1593500


def get_app_price(app_id: int, country: str = "GB") -> dict[str, Any] | None:
    """
    Fetch current Steam price for an app.

    Returns dict with price, original, discount, currency, url, name, is_free
    or None if not found / request failed.
    """
    params = {
        "appids": app_id,
        "cc": country.lower(),
        "filters": "price_overview",
    }
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    try:
        r = requests.get(STORE_API, params=params, headers=headers, timeout=12)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError):
        return None

    entry = data.get(str(app_id)) or data.get(app_id)
    if not entry or not entry.get("success"):
        return None

    app_data = entry.get("data") or {}
    overview = app_data.get("price_overview")

    # Free or no price listed
    if not overview:
        return {
            "app_id": app_id,
            "name": app_data.get("name") or f"App {app_id}",
            "price": Decimal("0.00"),
            "original": Decimal("0.00"),
            "discount": 0,
            "currency": "GBP" if country.upper() == "GB" else "EUR",
            "is_free": True,
            "url": f"https://store.steampowered.com/app/{app_id}/",
        }

    return {
        "app_id": app_id,
        "name": app_data.get("name") or f"App {app_id}",
        "price": Decimal(overview["final"]) / 100,
        "original": Decimal(overview["initial"]) / 100,
        "discount": int(overview.get("discount_percent") or 0),
        "currency": overview.get("currency") or "GBP",
        "is_free": False,
        "url": f"https://store.steampowered.com/app/{app_id}/",
    }


def get_god_of_war_steam(country: str = "GB") -> dict[str, Any] | None:
    """Convenience: God of War (2018) Steam price."""
    return get_app_price(GOD_OF_WAR_STEAM_APP_ID, country=country)
