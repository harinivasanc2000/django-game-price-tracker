"""
Steam Store public API client (no key required).

- Search:  GET /api/storesearch/?term=...&cc=GB
- Details: GET /api/appdetails?appids=...&cc=GB

Be polite (~200 req / 5 min). Cache in the app layer when possible.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import requests

STORE_SEARCH = "https://store.steampowered.com/api/storesearch/"
STORE_DETAILS = "https://store.steampowered.com/api/appdetails"
USER_AGENT = "GamePriceTracker/0.1 (personal; polite)"


def search_store(term: str, country: str = "GB", limit: int = 24) -> list[dict[str, Any]]:
    """
    Search Steam Store by keyword.

    Returns list of dicts:
      app_id, name, tiny_image, price, original, discount, currency, platforms, url
    """
    term = (term or "").strip()
    if not term:
        return []

    params = {"term": term, "l": "english", "cc": country.lower()}
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    try:
        r = requests.get(STORE_SEARCH, params=params, headers=headers, timeout=12)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError):
        return []

    items = data.get("items") or []
    results = []
    for item in items[:limit]:
        if item.get("type") not in (None, "app", "game"):
            # still include apps; skip pure hardware if type is weird
            pass
        app_id = item.get("id")
        if not app_id:
            continue

        price_info = item.get("price") or {}
        final = price_info.get("final")
        initial = price_info.get("initial")
        currency = price_info.get("currency") or ("GBP" if country.upper() == "GB" else "USD")

        if final is not None:
            price = Decimal(final) / 100
            original = Decimal(initial) / 100 if initial is not None else price
            discount = 0
            if initial and initial > final and initial > 0:
                discount = int(round((1 - final / initial) * 100))
        else:
            price = Decimal("0.00")
            original = Decimal("0.00")
            discount = 0

        plats = item.get("platforms") or {}
        platform_list = [k for k, v in plats.items() if v]

        results.append(
            {
                "app_id": int(app_id),
                "name": item.get("name") or f"App {app_id}",
                "tiny_image": item.get("tiny_image") or "",
                "price": price,
                "original": original,
                "discount": discount,
                "currency": currency,
                "platforms": platform_list,
                "url": f"https://store.steampowered.com/app/{app_id}/",
            }
        )
    return results


def get_app_price(app_id: int, country: str = "GB") -> dict[str, Any] | None:
    """
    Full-ish appdetails for one app (price + name + header image).
    """
    params = {"appids": app_id, "cc": country.lower()}
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    try:
        r = requests.get(STORE_DETAILS, params=params, headers=headers, timeout=12)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError):
        return None

    entry = data.get(str(app_id)) or data.get(app_id)
    if not entry or not entry.get("success"):
        return None

    app_data = entry.get("data") or {}
    overview = app_data.get("price_overview")
    header = app_data.get("header_image") or ""
    # capsule fallback
    if not header:
        header = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"

    if not overview:
        return {
            "app_id": app_id,
            "name": app_data.get("name") or f"App {app_id}",
            "price": Decimal("0.00"),
            "original": Decimal("0.00"),
            "discount": 0,
            "currency": "GBP" if country.upper() == "GB" else "EUR",
            "is_free": bool(app_data.get("is_free")),
            "url": f"https://store.steampowered.com/app/{app_id}/",
            "header_image": header,
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
        "header_image": header,
    }
