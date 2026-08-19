"""
PlayStation Store (UK) and Amazon UK helpers.

Neither exposes a free official public price API for arbitrary titles.
We provide reliable deep-search links and register Store rows so prices
can be entered via admin / future APIs.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from apps.games.models import Store


def ensure_uk_stores() -> dict[str, Store]:
    specs = [
        (
            "steam",
            "Steam",
            Store.StoreType.OFFICIAL,
            "https://store.steampowered.com",
            "Official PC digital",
        ),
        (
            "psn-uk",
            "PlayStation Store (UK)",
            Store.StoreType.OFFICIAL,
            "https://store.playstation.com/en-gb/pages/latest",
            "Official PSN UK — no free bulk price API; use search link or admin price",
        ),
        (
            "amazon-uk",
            "Amazon UK",
            Store.StoreType.MARKETPLACE,
            "https://www.amazon.co.uk",
            "Amazon UK physical/digital — PA-API needs keys; deep-search links for now",
        ),
        (
            "humble",
            "Humble Store",
            Store.StoreType.AUTHORIZED,
            "https://www.humblebundle.com/store",
            "Often appears in CheapShark feed",
        ),
    ]
    out = {}
    for slug, name, stype, web, notes in specs:
        obj, _ = Store.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "store_type": stype,
                "website": web,
                "country": "GB",
                "notes": notes,
            },
        )
        out[slug] = obj
    return out


def psn_search_url(title: str) -> str:
    q = quote_plus((title or "").strip())
    return f"https://store.playstation.com/en-gb/search/{q}"


def amazon_uk_search_url(title: str, platform_hint: str = "") -> str:
    parts = [title.strip()]
    if platform_hint:
        parts.append(platform_hint)
    q = quote_plus(" ".join(parts))
    return f"https://www.amazon.co.uk/s?k={q}"


def external_links_for_title(title: str) -> list[dict]:
    """Cards for PSN / Amazon on the detail page."""
    ensure_uk_stores()
    return [
        {
            "name": "PlayStation Store (UK)",
            "slug": "psn-uk",
            "kind": "official",
            "note": "Official digital. Live prices via store page (no free public API).",
            "url": psn_search_url(title),
            "price": None,
            "currency": "GBP",
        },
        {
            "name": "Amazon UK",
            "slug": "amazon-uk",
            "kind": "marketplace",
            "note": "Physical & some digital. Search Amazon UK — API needs Amazon credentials.",
            "url": amazon_uk_search_url(title),
            "price": None,
            "currency": "GBP",
        },
        {
            "name": "Amazon UK (PS4)",
            "slug": "amazon-uk-ps4",
            "kind": "marketplace",
            "note": "Filtered search hint for PS4 discs.",
            "url": amazon_uk_search_url(title, "PS4"),
            "price": None,
            "currency": "GBP",
        },
        {
            "name": "Amazon UK (PS5)",
            "slug": "amazon-uk-ps5",
            "kind": "marketplace",
            "note": "Filtered search hint for PS5 discs.",
            "url": amazon_uk_search_url(title, "PS5"),
            "price": None,
            "currency": "GBP",
        },
    ]
