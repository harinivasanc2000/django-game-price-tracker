"""
Amazon UK public *search* page — BS4 only (no public API).

Product title, price, star rating, ASIN link. No seller PII.
Often WAF-blocked from datacenters → search_url fallback.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from urllib.parse import quote_plus

from apps.games.cache import cached
from apps.games.clients.scrape_filters import filter_source_dict
from apps.games.clients.scrape_utils import (
    fetch_html,
    parse_money,
    parse_rating,
    product_row,
    soup_from,
)
from apps.games.clients.title_match import filter_by_title


def search_url(title: str, extra: str = "") -> str:
    q = quote_plus(f"{title} {extra}".strip())
    return f"https://www.amazon.co.uk/s?k={q}&i=videogames"


def _search_amazon_uk_uncached(title: str, extra: str = "", limit: int = 8) -> dict[str, Any]:
    try:
        limit = max(1, min(int(limit), 10))
    except (TypeError, ValueError):
        limit = 8
    url = search_url(title, extra)
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}

    html, status = fetch_html(url, timeout=10, referer="https://www.amazon.co.uk/")
    if not html or status != 200:
        out["blocked"] = True
        return out

    soup = soup_from(html)
    rows: list[dict] = []
    cards = soup.select('div[data-component-type="s-search-result"]')
    if not cards:
        # Alternate markup some locales use
        cards = soup.select("[data-asin]")

    for card in cards:
        asin = (card.get("data-asin") or "").strip()
        if not asin:
            continue
        title_el = card.select_one("h2 a span, h2 span, h2 a")
        name = title_el.get_text(" ", strip=True) if title_el else ""
        if not name or len(name) < 3:
            continue

        whole = card.select_one(".a-price-whole")
        frac = card.select_one(".a-price-fraction")
        if whole:
            w = whole.get_text().replace(",", "").replace(".", "").strip()
            f = frac.get_text().strip() if frac else "00"
            price = parse_money(f"{w}.{f}")
        else:
            price_el = card.select_one(".a-price .a-offscreen, span.a-offscreen")
            price = parse_money(price_el.get_text() if price_el else "")

        rating = None
        rating_el = card.select_one("span.a-icon-alt, i.a-icon-star-small span")
        if rating_el:
            rating = parse_rating(rating_el.get_text())

        blob = name.lower()
        is_used = any(x in blob for x in ("used", "renewed", "refurbished", "pre-owned"))

        row = product_row(
            name=name,
            price=price,
            store_name="Amazon UK",
            url=f"https://www.amazon.co.uk/dp/{asin}",
            rating=rating,
            is_used=is_used,
        )
        if row:
            row["asin"] = asin
            row["condition"] = "used" if is_used else "new"
            rows.append(row)
        if len(rows) >= limit * 3:
            break

    rows = filter_by_title(rows, title, min_score=0.67)
    unique: list[dict] = []
    seen_asins: set[str] = set()
    for row in rows:
        asin = str(row.get("asin") or "")
        if asin and asin in seen_asins:
            continue
        if asin:
            seen_asins.add(asin)
        unique.append(row)
    rows = unique[:limit]
    out["results"] = rows
    out["blocked"] = len(rows) == 0
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
    title = " ".join(str(title or "").split())[:160]
    if not title:
        return {"results": [], "blocked": True, "search_url": search_url(title, extra)}
    lo = str(min_price) if min_price is not None else ""
    hi = str(max_price) if max_price is not None else ""
    cond = (condition or "").strip().lower()
    try:
        limit = max(1, min(int(limit), 10))
    except (TypeError, ValueError):
        limit = 8
    raw = cached(
        f"amazon:bs4:v4:{title.lower()}:{extra.strip().lower()}:{limit}",
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
