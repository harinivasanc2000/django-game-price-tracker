"""
CeX UK — public boxes JSON API (preferred over HTML scrape).

Base: https://wss2.cex.uk.webuy.io/v3/boxes
Low volume + Django cache. Soft-fail on errors.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from apps.games.cache import cached
from apps.games.clients.scrape_utils import fetch_json, product_row
from apps.games.clients.title_match import filter_by_title

API = "https://wss2.cex.uk.webuy.io/v3/boxes"
SEARCH_TTL = 1800


def _boxes_uncached(query: str, count: int = 24) -> list[dict[str, Any]]:
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


def search_boxes(query: str, count: int = 24) -> list[dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return []
    return cached(
        f"cex:api:v2:{query.lower()}:{count}",
        lambda: _boxes_uncached(query, count=count),
        timeout=SEARCH_TTL,
    )


def search_cex_products(
    title: str,
    platform: str = "",
    limit: int = 8,
) -> dict[str, Any]:
    """
    Normalized product rows for UK physical panel.
    Uses JSON API + strict title_match (no LEGO bleed).
    """
    from apps.games.clients.uk_stores import platform_query

    title = (title or "").strip()
    q = platform_query(title, platform) if platform else title
    search_url = f"https://uk.webuy.com/search?stext={q.replace(' ', '+')}"
    out: dict[str, Any] = {"results": [], "blocked": False, "search_url": search_url}
    if not title:
        out["blocked"] = True
        return out

    boxes = search_boxes(q, count=max(limit * 3, 20))
    rows: list[dict] = []
    for b in boxes:
        name = b.get("boxName") or ""
        try:
            price = Decimal(str(b.get("sellPrice")))
        except (InvalidOperation, TypeError, ValueError):
            continue
        box_id = b.get("boxId")
        href = (
            f"https://uk.webuy.com/product-detail?id={box_id}"
            if box_id
            else search_url
        )
        rating = None
        try:
            if b.get("boxRating") is not None:
                rating = float(b["boxRating"])
        except (TypeError, ValueError):
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
            rows.append(row)

    rows = filter_by_title(rows, title, min_score=0.67)[:limit]
    out["results"] = rows
    out["blocked"] = len(rows) == 0
    return out
