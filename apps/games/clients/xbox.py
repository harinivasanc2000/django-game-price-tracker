"""
Xbox / Microsoft Store (GB) — lightweight public search.

Uses Microsoft displaycatalog autosuggest (no API key).
Soft-fail + cache. Product fields only.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from urllib.parse import quote_plus

import requests

from apps.games.cache import cached

UA = "GamePriceTracker/0.3 (personal; public data)"
AUTOSUGGEST = (
    "https://displaycatalog.mp.microsoft.com/v7.0/productFamilies/autosuggest"
)
PRODUCTS = "https://displaycatalog.mp.microsoft.com/v7.0/products"


def xbox_search_url(title: str) -> str:
    q = quote_plus((title or "").strip())
    return f"https://www.xbox.com/en-GB/search?q={q}"


def microsoft_store_search_url(title: str) -> str:
    q = quote_plus((title or "").strip())
    return f"https://www.microsoft.com/en-gb/search/shop/games?q={q}"


def _price_from_sku(sku: dict) -> tuple[Decimal | None, str]:
    try:
        avail = (sku.get("Availabilities") or [None])[0] or {}
        order = avail.get("OrderManagementData") or {}
        price = order.get("Price") or {}
        amount = price.get("ListPrice")
        if amount is None:
            amount = price.get("MSRP")
        if amount is None:
            return None, "GBP"
        return Decimal(str(amount)), (price.get("CurrencyCode") or "GBP").upper()
    except Exception:
        return None, "GBP"


def _search_xbox_uncached(title: str, limit: int = 8) -> list[dict[str, Any]]:
    headers = {"User-Agent": UA, "Accept": "application/json"}
    try:
        r = requests.get(
            AUTOSUGGEST,
            params={
                "market": "GB",
                "languages": "en-GB",
                "query": title,
            },
            headers=headers,
            timeout=8,
        )
        if r.status_code != 200:
            return []
        data = r.json() or {}
    except (requests.RequestException, ValueError):
        return []

    candidates: list[dict] = []
    if isinstance(data, list):
        candidates = [x for x in data if isinstance(x, dict)]
    elif isinstance(data, dict):
        for key in ("ResultSets", "Results", "ProductFamilies", "products"):
            block = data.get(key)
            if isinstance(block, list):
                candidates.extend([x for x in block if isinstance(x, dict)])
            elif isinstance(block, dict):
                inner = block.get("Suggests") or block.get("Products") or []
                if isinstance(inner, list):
                    candidates.extend([x for x in inner if isinstance(x, dict)])

    out: list[dict[str, Any]] = []
    seen = set()
    for item in candidates:
        name = (
            item.get("Title")
            or item.get("ProductTitle")
            or item.get("Name")
            or item.get("title")
            or ""
        )
        name = str(name).strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        product_id = (
            item.get("ProductId")
            or item.get("BigId")
            or item.get("Id")
            or item.get("productId")
            or ""
        )
        product_id = str(product_id)

        price = None
        currency = "GBP"
        for key in ("Price", "DisplayPrice", "ListPrice"):
            if item.get(key) is not None:
                try:
                    price = Decimal(str(item[key]).replace("£", "").replace(",", ""))
                    break
                except Exception:
                    pass

        url = xbox_search_url(name)
        if product_id:
            url = f"https://www.xbox.com/en-GB/games/store/x/{product_id}"

        row: dict[str, Any] = {
            "name": name[:200],
            "price": price if price is not None else None,
            "currency": currency,
            "product_id": product_id,
            "url": url,
            "store_name": "Xbox / Microsoft Store",
            "platform": "xbox",
            "image": item.get("ImageUrl") or item.get("Image") or "",
            "has_price": price is not None and price > 0,
        }
        out.append(row)
        if len(out) >= limit:
            break

    ids = [r["product_id"] for r in out if r.get("product_id") and not r.get("has_price")]
    if ids:
        try:
            pr = requests.get(
                PRODUCTS,
                params={
                    "bigIds": ",".join(ids[:8]),
                    "market": "GB",
                    "languages": "en-GB",
                },
                headers=headers,
                timeout=8,
            )
            if pr.status_code == 200:
                pdata = pr.json() or {}
                products = pdata.get("Products") or []
                by_id = {str(p.get("ProductId") or ""): p for p in products}
                for row in out:
                    p = by_id.get(row.get("product_id") or "")
                    if not p:
                        continue
                    skus = p.get("DisplaySkuAvailabilities") or []
                    if not skus:
                        continue
                    amount, cur = _price_from_sku(skus[0])
                    if amount is not None:
                        row["price"] = amount
                        row["currency"] = cur
                        row["has_price"] = amount > 0
                    loc = (p.get("LocalizedProperties") or [{}])[0]
                    if loc.get("ProductTitle"):
                        row["name"] = loc["ProductTitle"][:200]
        except (requests.RequestException, ValueError, KeyError):
            pass

    out.sort(
        key=lambda x: (
            not x.get("has_price"),
            float(x["price"]) if x.get("price") is not None else 9999,
        )
    )
    return out


def search_xbox(title: str, limit: int = 8) -> list[dict[str, Any]]:
    title = (title or "").strip()
    if not title:
        return []
    return cached(
        f"xbox:search:v2:{title.lower()}:{limit}",
        lambda: _search_xbox_uncached(title, limit),
        900,
    )
