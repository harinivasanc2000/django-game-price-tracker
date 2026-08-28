"""Reusable, bounded queries for current price snapshots.

PriceRecord is append-only history. A page that wants current offers must first
select the newest row for each (game, store) pair; otherwise an expired sale or
an arbitrary newest store can be presented as the current best deal.
"""

from __future__ import annotations

from collections.abc import Iterable

from django.db.models import OuterRef, QuerySet, Subquery

from .models import PriceRecord


def latest_store_snapshots(game_ids: Iterable[int]) -> QuerySet[PriceRecord]:
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
    return PriceRecord.objects.filter(
        game_id__in=ids,
        pk=Subquery(newest_for_store),
    ).select_related("game", "store")
