"""Reusable, bounded queries for current price snapshots.

PriceRecord is append-only history. A page that wants current offers must first
select the newest row for each (game, store) pair; otherwise an expired sale or
an arbitrary newest store can be presented as the current best deal.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta

from django.db.models import OuterRef, QuerySet, Subquery
from django.utils import timezone

from .models import PriceRecord

CURRENT_QUOTE_MAX_AGE = timedelta(days=7)


def latest_store_snapshots(
    game_ids: Iterable[int],
    *,
    max_age: timedelta | None = CURRENT_QUOTE_MAX_AGE,
) -> QuerySet[PriceRecord]:
    """Return one newest PriceRecord per game/store for the supplied games.

    The correlated subquery runs in SQL and avoids the classic N+1 loop where
    each game performs a separate latest-price query.
    """
    ids = list(dict.fromkeys(int(game_id) for game_id in game_ids))
    if not ids:
        return PriceRecord.objects.none()

    newest_for_store = (
        PriceRecord.objects.filter(
            game_id=OuterRef("game_id"), store_id=OuterRef("store_id")
        )
        .order_by("-recorded_at", "-pk")
        .values("pk")[:1]
    )
    current = PriceRecord.objects.filter(
        game_id__in=ids,
        pk=Subquery(newest_for_store),
    )
    # A disappeared or blocked listing cannot prove a sold-out transition.
    # Expire its last quote instead of presenting it as a live deal forever.
    if max_age is not None:
        current = current.filter(recorded_at__gte=timezone.now() - max_age)
    return current.select_related("game", "store")
