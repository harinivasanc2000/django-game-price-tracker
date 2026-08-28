"""
MusicMagpie UK — public product search (used games / media).
No login. Soft-fail → search_url fallback.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote_plus

from apps.games.cache import cached
from apps.games.clients.scrape_utils import (
    extract_ld_json_products,
    fetch_html,
    normalise_public_url,
    parse_money,
    product_row,
    soup_from,
)
from apps.games.clients.title_match import filter_by_title


def search_url(title: str, platform: str = "") -> str:
    from apps.games.clients.uk_stores import platform_query

    q = platform_query(title, platform) if platform else title
    return f"https://www.musicmagpie.co.uk/store/search?q={quote_plus(q)}"


def _search_uncached(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    try:
        limit = max(1, min(int(limit), 10))
    except (TypeError, ValueError):
        limit = 8
    url = search_url(title, platform)
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": url}
    html, _ = fetch_html(url, timeout=7, referer="https://www.musicmagpie.co.uk/")
    if not html:
        out["blocked"] = True
        return out

    soup = soup_from(html)
    rows: list[dict] = []

    for item in extract_ld_json_products(soup, limit=limit * 2):
        try:
            price = Decimal(str(item["price"]))
        except (InvalidOperation, KeyError, TypeError):
            continue
        if str(item.get("currency") or "GBP").upper() != "GBP":
            continue
        href = normalise_public_url(
            item.get("url"), base_url=url, allowed_hosts=("musicmagpie.co.uk",)
        ) or url
        row = product_row(
            name=item.get("name", ""),
            price=price,
            store_name="MusicMagpie",
            url=href,
            is_used=True,
        )
        if row:
            row["condition"] = "used"
            rows.append(row)

    if len(rows) < limit:
        for card in soup.select(
            ".product, article, [class*='product'], [class*='Product'], li"
        )[: limit + 24]:
            a = card.find("a", href=True)
            name_el = card.find(["h2", "h3", "a", "span"], class_=re.compile(r"name|title", re.I))
            name = (name_el or a).get_text(" ", strip=True) if (name_el or a) else ""
            if len(name) < 3:
                continue
            price_el = card.find(class_=re.compile(r"price", re.I))
            price = parse_money(
                price_el.get_text() if price_el else card.get_text(" ", strip=True),
                require_currency=price_el is None,
            )
            href = normalise_public_url(
                a.get("href") if a else "",
                base_url=url,
                allowed_hosts=("musicmagpie.co.uk",),
            ) or url
            row = product_row(
                name=name, price=price, store_name="MusicMagpie", url=href, is_used=True
            )
            if row:
                row["condition"] = "used"
                rows.append(row)
            if len(rows) >= limit * 3:
                break

    rows = filter_by_title(rows, title, min_score=0.67)
    deduped: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = ((row.get("name") or "").casefold(), row.get("url") or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    rows = deduped[:limit]
    out["results"] = rows
    out["blocked"] = len(rows) == 0
    return out


def try_musicmagpie(title: str, platform: str = "", limit: int = 8) -> dict[str, Any]:
    title = re.sub(r"\s+", " ", str(title or "")).strip()[:160]
    if not title:
        return {"results": [], "blocked": True, "search_url": ""}
    return cached(
        f"mmagpie:v2:{title.lower()}:{platform}:{limit}",
        lambda: _search_uncached(title, platform=platform, limit=limit),
        timeout=1800,
    )
