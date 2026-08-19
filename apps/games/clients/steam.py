"""
Steam Store public API client (no key required).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import requests

STORE_SEARCH = "https://store.steampowered.com/api/storesearch/"
STORE_DETAILS = "https://store.steampowered.com/api/appdetails"
USER_AGENT = "GamePriceTracker/0.1 (personal; polite)"

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
    "yakuza": ["Yakuza", "Like a Dragon"],
    "kiwami": ["Yakuza Kiwami"],
}

DLC_HINTS = (
    "dlc", "soundtrack", "ost", "cosmetic", "skin pack", "weapon pack",
    "season pass", "expansion pass", "bonus content", "digital artbook",
    "art book", "wallpapers", "avatar", "theme", "upgrade",
    "pre-order bonus", "preorder",
)


def expand_query(term: str) -> list[str]:
    raw = (term or "").strip()
    if not raw:
        return []
    key = raw.lower()
    terms = []
    if key in SEARCH_ALIASES:
        terms.extend(SEARCH_ALIASES[key])
    # partial alias match (e.g. "gta san")
    for ak, vals in SEARCH_ALIASES.items():
        if key.startswith(ak + " ") or key.startswith(ak):
            terms.extend(vals)
    terms.append(raw)
    seen, out = set(), []
    for t in terms:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def _looks_like_dlc(name: str) -> bool:
    n = (name or "").lower()
    return any(h in n for h in DLC_HINTS)


def _score_result(item: dict, query: str) -> int:
    name = (item.get("name") or "").lower()
    q = query.lower().strip()
    tokens = [t for t in q.replace(":", " ").split() if t]
    score = 0
    if _looks_like_dlc(name):
        score -= 50
    if name == q:
        score += 80
    elif name.startswith(q):
        score += 40
    if q in name:
        score += 20
    # multi-word: all tokens present
    if tokens:
        hits = sum(1 for t in tokens if t in name)
        score += hits * 12
        if hits == len(tokens):
            score += 25
    score -= min(len(name) // 12, 12)
    if item.get("price"):
        score += 3
    return score


def _parse_price_block(price_info: dict | None, is_free_flag: bool, country: str) -> dict:
    """
    Normalize Steam price fields.
    price_status: paid | free | unknown
    - free only if Steam marks is_free OR explicit free price
    - missing price_overview is usually region/unavailable — NOT free
    """
    currency = "GBP" if country.upper() == "GB" else "USD"
    if price_info:
        final = price_info.get("final")
        initial = price_info.get("initial")
        currency = price_info.get("currency") or currency
        if final is not None:
            price = Decimal(final) / 100
            original = Decimal(initial) / 100 if initial is not None else price
            discount = 0
            if initial and initial > final and initial > 0:
                discount = int(round((1 - final / initial) * 100))
            if final == 0 and is_free_flag:
                status = "free"
            elif final == 0:
                status = "unknown"  # zero without is_free is suspicious
            else:
                status = "paid"
            return {
                "price": price,
                "original": original,
                "discount": discount,
                "currency": currency,
                "price_status": status,
                "is_free": status == "free",
            }
    if is_free_flag:
        return {
            "price": Decimal("0.00"),
            "original": Decimal("0.00"),
            "discount": 0,
            "currency": currency,
            "price_status": "free",
            "is_free": True,
        }
    return {
        "price": None,
        "original": None,
        "discount": 0,
        "currency": currency,
        "price_status": "unknown",
        "is_free": False,
    }


def search_store(term: str, country: str = "GB", limit: int = 30) -> list[dict[str, Any]]:
    queries = expand_query(term)
    if not queries:
        return []

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    merged: dict[int, dict] = {}

    for q in queries[:4]:
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

            parsed = _parse_price_block(item.get("price"), False, country)
            name = item.get("name") or f"App {app_id}"
            plats = item.get("platforms") or {}
            merged[app_id] = {
                "app_id": app_id,
                "name": name,
                "tiny_image": item.get("tiny_image") or "",
                "price": parsed["price"],
                "original": parsed["original"],
                "discount": parsed["discount"],
                "currency": parsed["currency"],
                "price_status": parsed["price_status"],
                "is_free": parsed["is_free"],
                "platforms": [k for k, v in plats.items() if v],
                "url": f"https://store.steampowered.com/app/{app_id}/",
                "is_likely_dlc": _looks_like_dlc(name),
                "_score": _score_result(item, term),
            }

    results = sorted(merged.values(), key=lambda x: (-x["_score"], x["name"]))
    for r in results:
        r.pop("_score", None)
    return results[:limit]


def suggest_store(term: str, country: str = "GB", limit: int = 8) -> list[dict[str, Any]]:
    """Lightweight suggestions for typeahead (Netflix-style)."""
    term = (term or "").strip()
    if len(term) < 2:
        return []
    rows = search_store(term, country=country, limit=limit)
    return [
        {
            "app_id": r["app_id"],
            "name": r["name"],
            "tiny_image": r["tiny_image"],
            "price_status": r["price_status"],
            "price": str(r["price"]) if r["price"] is not None else None,
            "currency": r["currency"],
            "is_likely_dlc": r["is_likely_dlc"],
        }
        for r in rows
    ]


def get_app_details(app_id: int, country: str = "GB") -> dict[str, Any] | None:
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
    is_free_flag = bool(app_data.get("is_free"))

    platforms = []
    plat = app_data.get("platforms") or {}
    for k in ("windows", "mac", "linux"):
        if plat.get(k):
            platforms.append(k)

    release = (app_data.get("release_date") or {}).get("date") or ""
    coming_soon = bool((app_data.get("release_date") or {}).get("coming_soon"))

    parsed = _parse_price_block(overview, is_free_flag, country)
    if coming_soon and parsed["price_status"] == "unknown":
        price_note = "Coming soon — price not listed yet"
    elif parsed["price_status"] == "unknown":
        price_note = "Price not listed (region, package-only, or unavailable) — not necessarily free"
    elif parsed["price_status"] == "free":
        price_note = "Marked free on Steam"
    else:
        price_note = ""

    # List / sale baseline from Steam (not always historic launch MSRP)
    list_price = parsed["original"]
    current = parsed["price"]

    fullgame = app_data.get("fullgame") or {}
    parent_id = fullgame.get("appid")

    return {
        "app_id": app_id,
        "name": app_data.get("name") or f"App {app_id}",
        "type": app_type,
        "is_dlc": is_dlc,
        "price": current,
        "original": list_price,
        "list_price": list_price,
        "discount": parsed["discount"],
        "currency": parsed["currency"],
        "price_status": parsed["price_status"],
        "is_free": parsed["is_free"],
        "price_note": price_note,
        "coming_soon": coming_soon,
        "url": f"https://store.steampowered.com/app/{app_id}/",
        "header_image": header,
        "short_description": app_data.get("short_description") or "",
        "platforms": platforms,
        "release_date": release,
        "developers": app_data.get("developers") or [],
        "publishers": app_data.get("publishers") or [],
        "dlc_ids": app_data.get("dlc") or [],
        "parent_app_id": int(parent_id) if parent_id else None,
        "parent_name": fullgame.get("name") or "",
        "categories": [c.get("description") for c in (app_data.get("categories") or []) if c.get("description")],
        "genres": [g.get("description") for g in (app_data.get("genres") or []) if g.get("description")],
        "launch_price_note": (
            "Steam does not expose historic launch MSRP via public API. "
            "We use the current list/initial price as retail baseline. "
            "True launch price needs ITAD/GG.deals or manual entry later."
        ),
    }


def get_app_price(app_id: int, country: str = "GB") -> dict[str, Any] | None:
    return get_app_details(app_id, country=country)
