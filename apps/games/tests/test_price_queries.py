"""Regression tests for set-based current-offer selection."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.games.models import Game, PriceRecord, Store
from apps.games.price_queries import latest_store_snapshots, quote_needs_refresh


class LatestStoreSnapshotTests(TestCase):
    def test_returns_each_stores_newest_row_in_one_query(self):
        """An expired price is excluded without falling back to one query per game."""
        game = Game.objects.create(title="Current offers", slug="current-offers")
        steam = Store.objects.create(name="Steam", slug="steam")
        gog = Store.objects.create(name="GOG", slug="gog")

        old = PriceRecord.objects.create(game=game, store=steam, price=Decimal("4.99"))
        current = PriceRecord.objects.create(game=game, store=steam, price=Decimal("14.99"))
        other = PriceRecord.objects.create(game=game, store=gog, price=Decimal("11.99"))
        PriceRecord.objects.filter(pk=old.pk).update(
            recorded_at=timezone.now() - timedelta(days=2)
        )

        with self.assertNumQueries(1):
            rows = list(latest_store_snapshots([game.pk, game.pk]))

        self.assertCountEqual([row.pk for row in rows], [current.pk, other.pk])
        # ``select_related`` is part of the helper's contract for card pages.
        with self.assertNumQueries(0):
            self.assertEqual({row.store.name for row in rows}, {"Steam", "GOG"})

    def test_empty_game_list_does_not_hit_database(self):
        with self.assertNumQueries(0):
            self.assertEqual(list(latest_store_snapshots([])), [])

    def test_expired_latest_quote_is_not_current(self):
        game = Game.objects.create(title="Stale offers", slug="stale-offers")
        store = Store.objects.create(name="Old shop", slug="old-shop")
        stale = PriceRecord.objects.create(game=game, store=store, price=Decimal("9.99"))
        stale_at = timezone.now() - timedelta(days=8)
        PriceRecord.objects.filter(pk=stale.pk).update(
            recorded_at=stale_at,
            last_checked_at=stale_at,
        )

        self.assertEqual(list(latest_store_snapshots([game.pk])), [])
        self.assertEqual(list(latest_store_snapshots([game.pk], max_age=None)), [stale])

    def test_quote_warning_starts_after_twenty_four_hours(self):
        now = timezone.now()

        self.assertFalse(quote_needs_refresh(now - timedelta(hours=23), now=now))
        self.assertTrue(quote_needs_refresh(now - timedelta(hours=25), now=now))
