"""Client-side-safe sorting of Steam search result dicts."""
from __future__ import annotations

from decimal import Decimal
from typing import Any


def _price_key(r: dict[str, Any]) -> float:
    if r.get("price_status") == "free":
        return 0.0
    p = r.get("price")
    if p is None:
        return 1e12
    try:
        return float(p)
    except (TypeError, ValueError):
        return 1e12


def sort_results(results: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    sort = (sort or "relevance").strip().lower()
    if sort == "price_asc":
        return sorted(results, key=lambda r: (_price_key(r), r.get("name") or ""))
    if sort == "price_desc":
        return sorted(results, key=lambda r: (-_price_key(r), r.get("name") or ""))
    if sort == "discount":
        return sorted(
            results,
            key=lambda r: (-(r.get("discount") or 0), _price_key(r)),
        )
    if sort == "name":
        return sorted(results, key=lambda r: (r.get("name") or "").lower())
    return results
