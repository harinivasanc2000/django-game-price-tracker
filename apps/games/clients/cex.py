"""
CeX UK product search.

Strategy (project rule):
  1. Try the unofficial boxes JSON endpoint when it responds.
  2. If that is blocked / empty → BeautifulSoup the public search HTML.
  3. Soft-fail → search_url only (never raise).

No login. Public product fields only.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote_plus, urljoin

from apps.games.cache import cached
from apps.games.clients.scrape_utils import (
    fetch_html,
    fetch_json,
    parse_money,
    product_row,
    soup_from,
)
from apps.games.clients.title_match import filter_by_title

API = "https://wss2.cex.uk.webuy.io/v3/boxes"
SEARCH_TTL = 1800

_GAME_HINTS = (
    "game",
    "games",
    "software",
    "playstation",
    "xbox",
    "nintendo",
    "switch",
    "pc games",
    "sega",
    "retro",
)


def _boxes_api(query: str, count: int = 24) -> list[dict[str, Any]]:
    data, status = fetch_json(
        API,
        params={
            "q": query,
            "firstRecord": 1,
            "count": min(count, 50),
            "sortBy": "relevance",
            "sortOrder": "desc",
        },
        timeout=8,
    )
    if not data or status != 200:
        return []
    boxes = (
        (data.get("response") or {}).get("data", {}).get("boxes")
        or (data.get("data") or {}).get("boxes")
        or data.get("boxes")
        or []
    )
    return boxes if isinstance(boxes, list) else []


def _boxes_bs4(query: str, limit: int = 24) -> list[dict[str, Any]]:
    """Public search page HTML when the JSON endpoint is blocked."""
    url = f"https://uk.webuy.com/search?stext={quote_plus(query)}"
    html, _ = fetch_html(url, timeout=8, referer="https://uk.webuy.com/")
    if not html:
        return []

    soup = soup_from(html)
    boxes: list[dict[str, Any]] = []

    # Embedded JSON often still present in the SPA payload
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if "sellPrice" not in text or "boxName" not in text:
            continue
        for m in re.finditer(
            r'"boxName"\s*:\s*"([^"]+)".{0,500}?"sellPrice"\s*:\s*([0-9.]+)',
            text,
            re.DOTALL,
        ):
            box: dict[str, Any] = {
                "boxName": m.group(1),
                "sellPrice": m.group(2),
                "outOfStock": 0,
            }
            id_m = re.search(
                r'"boxId"\s*:\s*"?([A-Za-z0-9]+)"?',
                text[m.start() : m.start() + 900],
            )
            if id_m:
                box["boxId"] = id_m.group(1)
            boxes.append(box)
            if len(boxes) >= limit:
                return boxes

    # Card fallback
    for card in soup.select("[class*='product'], [class*='search-product'], .superbox, article")[
        : limit + 16
    ]:
        name_el = card.find(["h2", "h3", "a"], class_=re.compile(r"name|title", re.I))
        if not name_el:
            name_el = card.find("a", href=True)
        name = name_el.get_text(" ", strip=True) if name_el else ""
        price_el = card.find(string=re.compile(r"£\s*[0-9]"))
        if not price_el:
            price_el = card.find(class_=re.compile(r"price", re.I))
        price = parse_money(
            price_el if isinstance(price_el, str) else (price_el.get_text() if price_el else "")
        )
        if not name or price is None:
            continue
        href = url
        if name_el and getattr(name_el, "name", None) == "a" and name_el.get("href"):
            href = urljoin(url, name_el["href"])
        boxes.append(
            {
                "boxName": name,
                "sellPrice": str(price),
                "boxId": None,
                "_url": href,
                "outOfStock": 0,
            }
        )
        if len(boxes) >= limit:
            break

    return boxes


def search_boxes(query: str, count: int = 24) -> list[dict[str, Any]]:
    """API first; if blocked/empty → BS4 HTML."""
    query = (query or "").strip()
    if not query:
        return []

    def produce():
        boxes = _boxes_api(query, count=count)
        if boxes:
            return boxes
        # Blocked or empty unofficial API → public search page via BS4
        return _boxes_bs4(query, limit=count)

    return cached(
        f"cex:boxes:v4:{query.lower()}:{count}",
        produce,
        timeout=SEARCH_TTL,
    )


def _looks_like_game(box: dict) -> bool:
    blob = " ".join(
        str(box.get(k) or "")
        for k in ("categoryName", "categoryFriendlyName", "superCatName", "superCatFriendlyName")
    ).lower()
    if not blob.strip():
        return True
    return any(h in blob for h in _GAME_HINTS)


def search_cex_products(
    title: str,
    platform: str = "",
    limit: int = 8,
) -> dict[str, Any]:
    from apps.games.clients.uk_stores import platform_query

    title = (title or "").strip()
    q = platform_query(title, platform) if platform else title
    search_url = f"https://uk.webuy.com/search?stext={quote_plus(q)}"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": search_url}
    if not title:
        out["blocked"] = True
        return out

    boxes = search_boxes(q, count=max(limit * 4, 24))
    rows: list[dict] = []
    for b in boxes:
        if not _looks_like_game(b):
            continue
        name = b.get("boxName") or ""
        try:
            price = Decimal(str(b.get("sellPrice")))
        except (InvalidOperation, TypeError, ValueError):
            continue
        box_id = b.get("boxId")
        href = b.get("_url") or (
            f"https://uk.webuy.com/product-detail?id={box_id}" if box_id else search_url
        )
        rating = None
        try:
            if b.get("boxRating") is not None:
                rating = float(b["boxRating"])
        except (TypeError, ValueError):
            pass

        in_stock = not bool(b.get("outOfStock") or b.get("outOfEcomStock"))
        cash = None
        try:
            if b.get("cashPrice") is not None:
                cash = float(Decimal(str(b["cashPrice"])))
        except (InvalidOperation, TypeError, ValueError):
            pass

        row = product_row(
            name=name,
            price=price,
            store_name="CeX",
            url=href,
            rating=rating,
            is_used=True,
        )
        if row:
            row["condition"] = "used"
            row["in_stock"] = in_stock
            if cash is not None:
                row["trade_in_cash"] = cash
            if b.get("categoryFriendlyName") or b.get("categoryName"):
                row["category"] = b.get("categoryFriendlyName") or b.get("categoryName")
            rows.append(row)

    rows = filter_by_title(rows, title, min_score=0.67)[:limit]
    rows.sort(
        key=lambda r: (
            0 if r.get("in_stock") else 1,
            float(r["price"]) if r.get("price") is not None else 9999,
        )
    )
    out["results"] = rows[:limit]
    out["blocked"] = len(out["results"]) == 0
    return out
