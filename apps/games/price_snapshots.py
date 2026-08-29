"""Create compact price history without losing daily freshness.

Refresh jobs may run repeatedly with an unchanged price. Keeping every identical
row wastes storage and makes historical queries slower, so equal snapshots are
coalesced for a short window. A daily heartbeat is still retained so users can
see that an unchanged offer was checked recently.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone

from .clients.scrape_utils import normalise_public_url
from .models import Game, PriceRecord, Store

SNAPSHOT_HEARTBEAT = timedelta(hours=20)
MAX_STORED_PRICE = Decimal("99999999.99")


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _discount_or_none(value: Any) -> int | None:
    """Coerce untrusted API percentages into the model's valid 0–100 band."""
    if value in (None, ""):
        return None
    try:
        return max(0, min(int(round(float(value))), 100))
    except (TypeError, ValueError, OverflowError):
        return None


def record_snapshot(
    *,
    game: Game,
    store: Store,
    price: Any,
    currency: str = "GBP",
    original_price: Any = None,
    discount_percent: int | None = None,
    url: str = "",
    is_physical: bool = False,
    is_used: bool = False,
    condition: str = "",
    in_stock: bool = True,
    notes: str = "",
) -> tuple[PriceRecord, bool]:
    """Return `(record, created)` and coalesce an equal recent snapshot."""
    normalized = {
        "price": _decimal_or_none(price),
        "currency": (currency or "GBP").upper()[:3],
        "original_price": _decimal_or_none(original_price),
        "discount_percent": _discount_or_none(discount_percent),
        # Programmatic model writes bypass URLField form validation.  Reject
        # javascript:/data: schemes here before a value becomes a persistent
        # clickable link on comparison, deal, guide, or alert pages.
        "url": normalise_public_url(url)[:1000],
        "is_physical": bool(is_physical),
        "is_used": bool(is_used),
        "condition": (condition or "")[:50],
        "in_stock": bool(in_stock),
        "notes": (notes or "")[:255],
    }
    if (
        normalized["price"] is None
        or normalized["price"] < 0
        or normalized["price"] > MAX_STORED_PRICE
    ):
        raise ValueError("A price snapshot requires a finite, in-range, non-negative price.")
    if (
        normalized["original_price"] is not None
        and (
            normalized["original_price"] < 0
            or normalized["original_price"] > MAX_STORED_PRICE
        )
    ):
        raise ValueError("Original price must be finite, in-range, and non-negative.")

    # Lock the stable parent row while comparing/inserting. Two workers can
    # otherwise both observe the same old snapshot and insert duplicates. The
    # short transaction contains no network work and serialises only one game.
    with transaction.atomic():
        Game.objects.select_for_update().only("pk").get(pk=game.pk)
        latest = (
            PriceRecord.objects.filter(game=game, store=store)
            .order_by("-recorded_at", "-pk")
            .first()
        )
        if latest and latest.recorded_at >= timezone.now() - SNAPSHOT_HEARTBEAT:
            comparable = (
                latest.price == normalized["price"]
                and latest.currency == normalized["currency"]
                and latest.original_price == normalized["original_price"]
                and latest.discount_percent == normalized["discount_percent"]
                and latest.url == normalized["url"]
                and latest.is_physical == normalized["is_physical"]
                and latest.is_used == normalized["is_used"]
                and latest.condition == normalized["condition"]
                and latest.in_stock == normalized["in_stock"]
            )
            if comparable:
                return latest, False

        return PriceRecord.objects.create(game=game, store=store, **normalized), True
