"""Deterministic, defensive sorting for storefront search result dictionaries.

Store APIs do not agree on missing prices, numeric types, or relevance fields.
The helpers in this module normalise those differences before sorting so an
``unknown``/NaN price can never accidentally outrank a real UK price.
"""
from __future__ import annotations

import math
import unicodedata
from typing import Any


VALID_SORTS = frozenset(
    {
        "relevance",
        "match",
        "price_asc",
        "price_desc",
        "discount",
        "savings",
        "value",
        "name",
    }
)


def normalise_sort(value: str | None) -> str:
    """Return a supported sort name, falling back safely to relevance."""
    candidate = (value or "relevance").strip().lower()
    return candidate if candidate in VALID_SORTS else "relevance"


def _number(value: Any, default: float = 0.0) -> float:
    """Coerce API numeric values while rejecting NaN and infinity."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _name_key(result: dict[str, Any]) -> str:
    # NFKD/casefold gives stable ordering for names such as Ragnarök.
    name = unicodedata.normalize("NFKD", str(result.get("name") or ""))
    return "".join(ch for ch in name if not unicodedata.combining(ch)).casefold()


def _known_price(result: dict[str, Any]) -> float | None:
    """Return a usable non-negative price, or ``None`` when it is unknown."""
    status = str(result.get("price_status") or "").lower()
    if status == "free":
        return 0.0
    if status == "unknown" or result.get("has_price") is False:
        return None

    value = result.get("price")
    try:
        price = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(price) or price < 0:
        return None
    return price


def _price_key(result: dict[str, Any]) -> float:
    price = _known_price(result)
    return price if price is not None else math.inf


def _match_key(result: dict[str, Any]) -> float:
    return max(0.0, min(_number(result.get("match_score")), 1.0))


def _discount_key(result: dict[str, Any]) -> float:
    return max(0.0, min(_number(result.get("discount")), 100.0))


def _saving_key(result: dict[str, Any]) -> float:
    """Calculate cash saving when a trustworthy original price is present."""
    price = _known_price(result)
    original = _number(result.get("original"), default=-1.0)
    if price is None or original <= price:
        return 0.0
    return original - price


def _value_score(result: dict[str, Any]) -> float:
    """Multi-objective deal score balancing match, discount and paid price.

    Match quality has the largest weight, preventing a cheap loosely related
    edition from beating the requested game. Discount and cash saving then add
    evidence of value; logarithmic price dampening rewards lower prices without
    letting a one-pound difference dominate relevance.
    """
    price = _known_price(result)
    if price is None:
        return -math.inf
    return (
        _match_key(result) * 160.0
        + _discount_key(result) * 0.35
        + min(_saving_key(result), 100.0) * 0.12
        - math.log1p(price) * 2.0
    )


def sort_results(results: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    """Return a new, stably sorted list without modifying API result rows."""
    mode = normalise_sort(sort)

    if mode == "price_asc":
        return sorted(results, key=lambda row: (_price_key(row), _name_key(row)))
    if mode == "price_desc":
        # The leading boolean is important: negating ``inf`` used to put
        # unknown prices before the most expensive real result.
        return sorted(
            results,
            key=lambda row: (
                _known_price(row) is None,
                -(_known_price(row) or 0.0),
                _name_key(row),
            ),
        )
    if mode == "discount":
        return sorted(
            results,
            key=lambda row: (
                -_discount_key(row),
                _known_price(row) is None,
                _price_key(row),
                _name_key(row),
            ),
        )
    if mode == "savings":
        return sorted(
            results,
            key=lambda row: (
                -_saving_key(row),
                _known_price(row) is None,
                _price_key(row),
                _name_key(row),
            ),
        )
    if mode == "value":
        return sorted(
            results,
            key=lambda row: (-_value_score(row), _price_key(row), _name_key(row)),
        )
    if mode == "name":
        return sorted(results, key=_name_key)
    if mode == "match":
        return sorted(
            results,
            key=lambda row: (-_match_key(row), _price_key(row), _name_key(row)),
        )

    # Relevance uses the strict title matcher when available. Python's stable
    # sort preserves the upstream API order for rows with identical evidence.
    if any(row.get("match_score") is not None for row in results):
        return sorted(
            results,
            key=lambda row: (-_match_key(row), _price_key(row), _name_key(row)),
        )
    return list(results)
