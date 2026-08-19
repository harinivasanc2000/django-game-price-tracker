"""
PlayStation Store (UK) — public Chihiro tumbler search.

Endpoint (public JSON used by storefront search):
  GET /store/api/chihiro/00_09_000/tumbler/GB/en/999/{query}?suggested_size=N&mode=game

Polite use only; no bulk hammering.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from urllib.parse import quote

import requests

TUMBLER = (
    "https://store.playstation.com/store/api/chihiro/00_09_000/tumbler/"
    "GB/en/999/{query}"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def search_psn(title: str, limit: int = 10) -> list[dict[str, Any]]:
    title = (title or "").strip()
    if not title:
        return []

    url = TUMBLER.format(query=quote(title))
    params = {"suggested_size": max(limit, 8), "mode": "game"}
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Accept-Language": "en-GB,en;q=0.9",
    }

    try:
        r = requests.get(url, params=params, headers=headers, timeout=14)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError):
        return []

    results = []
    seen = set()
    for item in data.get("links") or []:
        sku = item.get("default_sku") or {}
        pid = item.get("id") or sku.get("id")
        if not pid or pid in seen:
            continue
        seen.add(pid)

        name = item.get("name") or sku.get("name") or "PlayStation title"
        content = item.get("game_contentType") or ""
        # Prefer full games; still include but flag others
        is_full = "full" in content.lower() or content == "Full Game"

        price_cents = sku.get("price")
        display = sku.get("display_price") or ""
        if price_cents is None and not display:
            continue

        if price_cents is not None:
            price = Decimal(price_cents) / 100
        else:
            # parse £12.99 style
            cleaned = display.replace("£", "").replace(",", "").strip()
            try:
                price = Decimal(cleaned)
            except Exception:
                continue

        platforms = []
        for p in sku.get("platforms") or []:
            # platform ids are opaque; prefer metadata
            pass
        meta = item.get("metadata") or {}
        playable = (meta.get("playable_platform") or {}).get("values") or []
        platforms = [str(x) for x in playable]

        # Image
        image = ""
        for img in item.get("images") or []:
            if img.get("url"):
                image = img["url"]
                break

        results.append(
            {
                "name": name,
                "price": price,
                "currency": "GBP",
                "display_price": display or f"£{price}",
                "product_id": pid,
                "content_type": content,
                "is_full_game": is_full,
                "platforms": platforms,
                "image": image,
                "url": f"https://store.playstation.com/en-gb/product/{pid}",
                "store_name": "PlayStation Store (UK)",
            }
        )
        if len(results) >= limit:
            break

    # Full games first
    results.sort(key=lambda x: (not x["is_full_game"], x["price"]))
    return results


def best_psn_deal(title: str) -> dict[str, Any] | None:
    rows = search_psn(title, limit=12)
    full = [r for r in rows if r["is_full_game"] and r["price"] > 0]
    if full:
        return full[0]
    paid = [r for r in rows if r["price"] > 0]
    return paid[0] if paid else (rows[0] if rows else None)
