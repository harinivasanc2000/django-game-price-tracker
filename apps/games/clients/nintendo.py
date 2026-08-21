"""
Nintendo eShop (UK) — polite public search.

Nintendo does not offer a stable public price API for all regions.
We try the UK search page lightly; always return an official search URL.

Product fields only (title, price, url).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from urllib.parse import quote_plus, urljoin

from apps.games.cache import cached
from apps.games.clients.scrape_utils import fetch_html, parse_money, product_row, soup_from

SEARCH = "https://www.nintendo.com/en-gb/Search/Search-299117.html?q={q}"
SEARCH_ALT = "https://www.nintendo.co.uk/Search/Search-299117.html?q={q}"


def nintendo_search_url(title: str) -> str:
    q = quote_plus((title or "").strip())
    return SEARCH.format(q=q)


def _search_nintendo_uncached(title: str, limit: int = 6) -> dict[str, Any]:
    url = nintendo_search_url(title)
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}

    html, status = fetch_html(url, timeout=8)
    if not html:
        alt = SEARCH_ALT.format(q=quote_plus(title))
        html, status = fetch_html(alt, timeout=8)
        if html:
            url = alt
            out["search_url"] = alt
    if not html:
        out["blocked"] = True
        return out

    soup = soup_from(html)
    cards = soup.select(
        ".search-result, .product-tile, .game-tile, article, li.res, [data-product-id]"
    )
    if not cards:
        cards = soup.find_all("a", href=True)

    for card in cards[: limit + 20]:
        a = card if getattr(card, "name", "") == "a" else card.find("a", href=True)
        if not a:
            continue
        href = a.get("href") or ""
        if not href or href.startswith("#"):
            continue
        name = a.get_text(" ", strip=True) or card.get_text(" ", strip=True)
        if len(name) < 3:
            continue
        low = href.lower()
        if not any(x in low for x in ("game", "software", "title", "product", "/games/")):
            if "nintendo" not in low:
                continue
        full = urljoin(url, href)
        price_el = None
        if hasattr(card, "find"):
            price_el = card.find(class_=lambda c: c and "price" in str(c).lower())
        price = parse_money(price_el.get_text() if price_el else card.get_text(" ", strip=True))
        # product_row rejects None price — use 0 + has_price flag for link-only rows
        row = product_row(
            name=name,
            price=price if price is not None else Decimal("0"),
            currency="GBP",
            url=full,
            store_name="Nintendo eShop (UK)",
        )
        if row:
            row["platform"] = "switch"
            row["has_price"] = price is not None and price > 0
            out["results"].append(row)
        if len(out["results"]) >= limit:
            break

    if not out["results"]:
        out["blocked"] = True
    else:
        out["results"].sort(
            key=lambda r: (not r.get("has_price"), float(r.get("price") or 9999))
        )
    return out


def search_nintendo(title: str, limit: int = 6) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return {"results": [], "blocked": True, "search_url": ""}
    return cached(
        f"nintendo:search:v2:{title.lower()}:{limit}",
        lambda: _search_nintendo_uncached(title, limit),
        900,
    )
