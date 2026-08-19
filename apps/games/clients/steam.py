"""
Steam Store public API client (no key required).

- Search:  GET /api/storesearch/?term=...&cc=GB
- Details: GET /api/appdetails?appids=...&cc=GB
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import requests

STORE_SEARCH = "https://store.steampowered.com/api/storesearch/"
STORE_DETAILS = "https://store.steampowered.com/api/appdetails"
USER_AGENT = "GamePriceTracker/0.1 (personal; polite)"

# Common abbreviations / alternate search terms
SEARCH_ALIASES: dict[str, list[str]] = {
    "gta": ["Grand Theft Auto", "GTA"],
    "gta5": ["Grand Theft Auto V", "GTA V"],
    "gta v": ["Grand Theft Auto V"],
    "gta 5": ["Grand Theft Auto V"],
    "cyberpunk": ["Cyberpunk 2077"],
    "cp2077": ["Cyberpunk 2077"],
    "rdr2": ["Red Dead Redemption 2"],
    "rdr": ["Red Dead Redemption"],
    "ac": ["Assassin's Creed"],
    "gow": ["God of War"],
    "tdm": ["Like a Dragon"],
    "yakuza": ["Yakuza", "Like a Dragon"],
}

DLC_HINTS = (
    "dlc",
    "soundtrack",
    "ost",
    "cosmetic",
    "skin pack",
    "weapon pack",
    "season pass",
    "expansion pass",
    "bonus content",
    "digital artbook",
    "art book",
    "wallpapers",
    "avatar",
    "theme",
    "upgrade",
    "pre-order bonus",
    "preorder",
)


def expand_query(term: str) -> list[str]:
    """Return search terms to try (alias expansions first)."""
    raw = (term or "").strip()
    if not raw:
        return []
    key = raw.lower()
    terms = []
    if key in SEARCH_ALIASES:
        terms.extend(SEARCH_ALIASES[key])
    terms.append(raw)
    # unique preserve order
    seen = set()
    out = []
    for t in terms:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def _looks_like_dlc(name: str) -> bool:
    n = (name or "").lower()
    return any(h in n for h in DLC_HINTS)


def _score_result(item: dict, query: str) -> int:
    """Higher = better. Prefer full games matching the query."""
    name = (item.get("name") or "").lower()
    q = query.lower()
    score = 0
    if _looks_like_dlc(name):
        score -= 50
    if name == q or name.startswith(q):
        score += 30
    if q in name:
        score += 15
    # Prefer shorter titles (base game often shorter than "Game - Season Pass")
    score -= min(len(name) // 10, 10)
    if item.get("price"):
        score += 2
    return score


def search_store(term: str, country: str = "GB", limit: int = 30) -> list[dict[str, Any]]:
    """
    Search Steam by keyword. Expands aliases (GTA, cyberpunk…).
    Sorts base games above DLC/extras.
    """
    queries = expand_query(term)
    if not queries:
        return []

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    merged: dict[int, dict] = {}

    for q in queries[:3]:
        params = {"term": q, "l": "english", "cc": country.lower()}
        try:
            r = requests.get(STORE_SEARCH, params=params, headers=headers, timeout=12)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError):
            continue

        for item in data.get("items") or []:
            app_id = item.get("id")
            if not app_id:
                continue
            app_id = int(app_id)
            if app_id in merged:
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

            name = item.get("name") or f"App {app_id}"
            plats = item.get("platforms") or {}
            merged[app_id] = {
                "app_id": app_id,
                "name": name,
                "tiny_image": item.get("tiny_image") or "",
                "price": price,
                "original": original,
                "discount": discount,
                "currency": currency,
                "platforms": [k for k, v in plats.items() if v],
                "url": f"https://store.steampowered.com/app/{app_id}/",
                "is_likely_dlc": _looks_like_dlc(name),
                "_score": _score_result(item, term),
            }

    results = sorted(merged.values(), key=lambda x: (-x["_score"], x["name"]))
    for r in results:
        r.pop("_score", None)
    return results[:limit]


def get_app_details(app_id: int, country: str = "GB") -> dict[str, Any] | None:
    """Full appdetails: type, price, images, platforms, release, dlc list."""
    params = {"appids": app_id, "cc": country.lower()}
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    try:
        r = requests.get(STORE_DETAILS, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError):
        return None

    entry = data.get(str(app_id)) or data.get(app_id)
    if not entry or not entry.get("success"):
        return None

    app_data = entry.get("data") or {}
    overview = app_data.get("price_overview")
    header = app_data.get("header_image") or (
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"
    )
    app_type = (app_data.get("type") or "game").lower()
    is_dlc = app_type == "dlc" or bool(app_data.get("fullgame"))

    platforms = []
    plat = app_data.get("platforms") or {}
    if plat.get("windows"):
        platforms.append("windows")
    if plat.get("mac"):
        platforms.append("mac")
    if plat.get("linux"):
        platforms.append("linux")

    release = (app_data.get("release_date") or {}).get("date") or ""

    if not overview:
        price = original = Decimal("0.00")
        discount = 0
        currency = "GBP" if country.upper() == "GB" else "EUR"
        is_free = bool(app_data.get("is_free"))
    else:
        price = Decimal(overview["final"]) / 100
        original = Decimal(overview["initial"]) / 100
        discount = int(overview.get("discount_percent") or 0)
        currency = overview.get("currency") or "GBP"
        is_free = False

    # Related full game if this is DLC
    fullgame = app_data.get("fullgame") or {}
    parent_id = fullgame.get("appid")
    parent_name = fullgame.get("name")

    return {
        "app_id": app_id,
        "name": app_data.get("name") or f"App {app_id}",
        "type": app_type,
        "is_dlc": is_dlc,
        "price": price,
        "original": original,
        "discount": discount,
        "currency": currency,
        "is_free": is_free,
        "url": f"https://store.steampowered.com/app/{app_id}/",
        "header_image": header,
        "short_description": app_data.get("short_description") or "",
        "platforms": platforms,
        "release_date": release,
        "developers": app_data.get("developers") or [],
        "publishers": app_data.get("publishers") or [],
        "dlc_ids": app_data.get("dlc") or [],
        "parent_app_id": int(parent_id) if parent_id else None,
        "parent_name": parent_name or "",
        "categories": [c.get("description") for c in (app_data.get("categories") or []) if c.get("description")],
        "genres": [g.get("description") for g in (app_data.get("genres") or []) if g.get("description")],
    }


# Backwards-compatible alias
def get_app_price(app_id: int, country: str = "GB") -> dict[str, Any] | None:
    return get_app_details(app_id, country=country)
