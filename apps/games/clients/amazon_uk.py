"""
Amazon UK public *search* page — product title, price, star rating, ASIN link.
No seller personal data. Often WAF-blocked from datacenters → search_url fallback.
Supports platform / price / condition post-filters (no login).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from urllib.parse import quote_plus

from apps.games.cache import cached
from apps.games.clients.scrape_filters import filter_source_dict, parse_price_bound
from apps.games.clients.scrape_utils import (
    fetch_html,
    parse_money,
    parse_rating,
    product_row,
    soup_from,
)


def search_url(title: str, extra: str = "") -> str:
    q = quote_plus(f"{title} {extra}".strip())
    return f"https://www.amazon.co.uk/s?k={q}&i=videogames"


def _search_amazon_uk_uncached(title: str, extra: str = "", limit: int = 8) -> dict[str, Any]:
    url = search_url(title, extra)
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}

    html, _ = fetch_html(url, timeout=12)
    if not html or "a-price" not in html:
        out["blocked"] = True
        return out

    soup = soup_from(html)
    cards = soup.select('div[data-component-type="s-search-result"]')
    for card in cards:
        asin = card.get("data-asin") or ""
        title_el = card.select_one("h2 a span, h2 span")
        name = title_el.get_text(" ", strip=True) if title_el else ""
        whole = card.select_one(".a-price-whole")
        frac = card.select_one(".a-price-fraction")
        if whole:
            w = whole.get_text().replace(",", "").replace(".", "").strip()
            f = frac.get_text().strip() if frac else "00"
            price = parse_money(f"{w}.{f}")
        else:
            price_el = card.select_one(".a-price .a-offscreen")
            price = parse_money(price_el.get_text() if price_el else "")

        rating = None
        rating_el = card.select_one("span.a-icon-alt, i.a-icon-star-small span")
        if rating_el:
            rating = parse_rating(rating_el.get_text())

        product_url = f"https://www.amazon.co.uk/dp/{asin}" if asin else url
        row = product_row(
            name=name,
            price=price,
            store_name="Amazon UK",
            url=product_url,
            rating=rating,
        )
        if row:
            if asin:
                row["asin"] = asin
            out["results"].append(row)
        if len(out["results"]) >= limit:
            break

    out["blocked"] = len(out["results"]) == 0
    return out


def search_amazon_uk(
    title: str,
    extra: str = "",
    limit: int = 8,
    *,
    platform: str = "",
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    condition: str = "",
) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        return {"results": [], "blocked": True, "search_url": search_url(title, extra)}
    lo = str(min_price) if min_price is not None else ""
    hi = str(max_price) if max_price is not None else ""
    cond = (condition or "").strip().lower()
    raw = cached(
        f"amazon:bs4:v2:{title.lower()}:{extra.strip().lower()}:{limit}",
        lambda: _search_amazon_uk_uncached(title, extra=extra, limit=limit),
        timeout=1800,
    )
    return filter_source_dict(
        raw,
        title=title,
        platform=platform or extra.lower(),
        min_price=min_price,
        max_price=max_price,
        condition=cond,
    )
