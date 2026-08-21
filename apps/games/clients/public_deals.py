"""
Public deal feeds for "what to buy / where".

- Steam store featuredcategories (GB) — specials + top sellers
- CheapShark /deals — multi-store PC digital with savings %
- Free / near-free highlights (salePrice ~ 0)

No API keys. Soft-fail + cache.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import requests

from apps.games.cache import cached
from apps.games.fx import to_gbp_or_zero

UA = "GamePriceTracker/0.2 (personal; public data only)"
STEAM_FEATURED = "https://store.steampowered.com/api/featuredcategories/"
CHEAPSHARK_DEALS = "https://www.cheapshark.com/api/1.0/deals"
CHEAPSHARK_STORES = "https://www.cheapshark.com/api/1.0/stores"

SAFER_STORES = {
    "steam",
    "gog",
    "humble store",
    "fanatical",
    "greenmangaming",
    "epic games store",
    "microsoft store",
}


def _steam_featured_uncached(country: str = "GB") -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {"specials": [], "top_sellers": [], "new_releases": []}
    try:
        r = requests.get(
            STEAM_FEATURED,
            params={"cc": country.lower(), "l": "english"},
            headers={"User-Agent": UA},
            timeout=12,
        )
        r.raise_for_status()
        data = r.json() or {}
    except (requests.RequestException, ValueError):
        return out

    def parse_items(key: str, bucket: str, limit: int = 12):
        block = data.get(key) or {}
        items = block.get("items") or []
        for it in items[:limit]:
            app_id = it.get("id") or it.get("appid")
            try:
                app_id = int(app_id)
            except (TypeError, ValueError):
                continue
            final_raw = it.get("final")
            original_raw = it.get("original")
            discount = it.get("discount_percent") or 0
            try:
                final = Decimal(final_raw) / Decimal(100) if final_raw is not None else None
            except Exception:
                final = None
            try:
                original = Decimal(original_raw) / Decimal(100) if original_raw is not None else None
            except Exception:
                original = None
            currency = (it.get("currency") or "GBP").upper()
            if final is None and it.get("final_price") is not None:
                try:
                    final = Decimal(it["final_price"]) / Decimal(100)
                except Exception:
                    pass
            title = (it.get("name") or "").strip()
            if not title:
                continue
            header = it.get("header_image") or (
                f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"
            )
            gbp = float(to_gbp_or_zero(final, currency)) if final is not None else None
            out[bucket].append(
                {
                    "source": "Steam",
                    "kind": "official",
                    "app_id": app_id,
                    "title": title,
                    "price": float(final) if final is not None else None,
                    "original": float(original) if original is not None else None,
                    "currency": currency,
                    "price_gbp": gbp,
                    "discount": int(discount) if discount else 0,
                    "image": header,
                    "url": f"https://store.steampowered.com/app/{app_id}/",
                    "detail_path": f"/steam/{app_id}/",
                    "advice": "Official Steam store — safest digital option when close to other prices.",
                }
            )

    parse_items("specials", "specials", 16)
    parse_items("top_sellers", "top_sellers", 12)
    parse_items("new_releases", "new_releases", 8)
    return out


def steam_featured(country: str = "GB") -> dict[str, list[dict[str, Any]]]:
    country = (country or "GB").upper()
    return cached(
        f"steam:featured:v1:{country}",
        lambda: _steam_featured_uncached(country),
        900,
    )


def _cheapshark_stores_uncached() -> dict[str, str]:
    try:
        r = requests.get(CHEAPSHARK_STORES, headers={"User-Agent": UA}, timeout=10)
        r.raise_for_status()
        return {str(s["storeID"]): s["storeName"] for s in r.json() if s.get("isActive")}
    except (requests.RequestException, ValueError, KeyError):
        return {}


def cheapshark_stores() -> dict[str, str]:
    return cached("cheapshark:stores:v2", _cheapshark_stores_uncached, 86400)


def _row_from_cheapshark_deal(d: dict, stores: dict[str, str]) -> dict[str, Any] | None:
    title = (d.get("title") or "").strip()
    if not title:
        return None
    try:
        price = Decimal(str(d.get("salePrice", "0")))
        retail = Decimal(str(d.get("normalPrice", "0")))
    except (InvalidOperation, ValueError):
        return None
    savings = int(round(float(d.get("savings") or 0)))
    sid = str(d.get("storeID", ""))
    store_name = stores.get(sid, f"Store {sid}")
    deal_id = d.get("dealID") or ""
    steam_app = d.get("steamAppID")
    try:
        steam_app = int(steam_app) if steam_app else None
    except (TypeError, ValueError):
        steam_app = None
    safer = store_name.lower() in SAFER_STORES
    gbp = float(to_gbp_or_zero(price, "USD")) if price > 0 else 0.0
    return {
        "source": "CheapShark",
        "kind": "official" if safer else "third-party",
        "app_id": steam_app,
        "title": title,
        "price": float(price),
        "original": float(retail) if retail else None,
        "currency": "USD",
        "price_gbp": gbp,
        "discount": savings,
        "store_name": store_name,
        "image": d.get("thumb") or "",
        "url": f"https://www.cheapshark.com/redirect?dealID={deal_id}" if deal_id else "",
        "detail_path": f"/steam/{steam_app}/" if steam_app else "",
        "metacritic": d.get("metacriticScore"),
        "advice": (
            "Official / major retailer — good first choice."
            if safer
            else "Third-party keyshop — check region & seller reputation before buying."
        ),
    }


def _cheapshark_top_uncached(limit: int = 24, upper_price: float = 40.0) -> list[dict[str, Any]]:
    stores = cheapshark_stores()
    try:
        r = requests.get(
            CHEAPSHARK_DEALS,
            params={
                "pageSize": min(limit, 60),
                "sortBy": "Savings",
                "desc": 1,
                "upperPrice": upper_price,
                "onSale": 1,
            },
            headers={"User-Agent": UA},
            timeout=14,
        )
        r.raise_for_status()
        rows = r.json() or []
    except (requests.RequestException, ValueError):
        return []

    out = []
    seen_titles = set()
    for d in rows:
        title = (d.get("title") or "").strip()
        if not title or title.lower() in seen_titles:
            continue
        try:
            price = Decimal(str(d.get("salePrice", "0")))
        except (InvalidOperation, ValueError):
            continue
        if price <= 0:
            continue
        row = _row_from_cheapshark_deal(d, stores)
        if not row:
            continue
        seen_titles.add(title.lower())
        out.append(row)
        if len(out) >= limit:
            break
    return out


def cheapshark_top_deals(limit: int = 24, upper_price: float = 40.0) -> list[dict[str, Any]]:
    return cached(
        f"cheapshark:top:v1:{limit}:{upper_price}",
        lambda: _cheapshark_top_uncached(limit, upper_price),
        600,
    )


def _free_pc_uncached(limit: int = 12) -> list[dict[str, Any]]:
    """Deals with sale price 0 (giveaways / free-to-claim keys)."""
    stores = cheapshark_stores()
    try:
        r = requests.get(
            CHEAPSHARK_DEALS,
            params={
                "pageSize": 40,
                "sortBy": "Savings",
                "desc": 1,
                "upperPrice": 0,
                "onSale": 1,
            },
            headers={"User-Agent": UA},
            timeout=14,
        )
        r.raise_for_status()
        rows = r.json() or []
    except (requests.RequestException, ValueError):
        return []

    out = []
    seen = set()
    for d in rows:
        title = (d.get("title") or "").strip()
        if not title or title.lower() in seen:
            continue
        try:
            price = Decimal(str(d.get("salePrice", "1")))
        except (InvalidOperation, ValueError):
            continue
        if price > 0:
            continue
        row = _row_from_cheapshark_deal(d, stores)
        if not row:
            continue
        row["price"] = 0.0
        row["price_gbp"] = 0.0
        row["advice"] = (
            "Listed free via aggregator — claim only on official store pages when possible; "
            "watch for region-locked keys."
        )
        seen.add(title.lower())
        out.append(row)
        if len(out) >= limit:
            break
    return out


def free_pc_deals(limit: int = 12) -> list[dict[str, Any]]:
    return cached(f"cheapshark:free:v1:{limit}", lambda: _free_pc_uncached(limit), 600)


def buy_recommendations(
    country: str = "GB",
    limit_steam: int = 10,
    limit_cs: int = 16,
) -> dict[str, Any]:
    """Combined public snapshot for the buy guide page."""
    featured = steam_featured(country=country)
    cs = cheapshark_top_deals(limit=limit_cs)
    free = free_pc_deals(limit=10)

    smart = sorted(
        [d for d in cs if (d.get("discount") or 0) >= 40],
        key=lambda d: (
            0 if d.get("kind") == "official" else 1,
            -(d.get("discount") or 0),
            d.get("price_gbp") or 999,
        ),
    )[:12]

    return {
        "steam_specials": (featured.get("specials") or [])[:limit_steam],
        "steam_top": (featured.get("top_sellers") or [])[:8],
        "steam_new": (featured.get("new_releases") or [])[:6],
        "multi_store": cs,
        "smart_picks": smart,
        "free_picks": free,
        "country": country,
    }
