"""Compact history must preserve changes while coalescing repeat refreshes."""

from decimal import Decimal

from django.test import TestCase

from apps.games.models import Game, PriceRecord, Store
from apps.games.price_snapshots import record_snapshot


class PriceSnapshotTests(TestCase):
    def setUp(self):
        self.game = Game.objects.create(title="Snapshot", slug="snapshot", platform=Game.Platform.PC)
        self.store = Store.objects.create(name="Steam", slug="steam")

    def test_identical_recent_snapshot_is_coalesced(self):
        first, created_first = record_snapshot(
            game=self.game, store=self.store, price="9.99", url="https://example.test/game"
        )
        second, created_second = record_snapshot(
            game=self.game, store=self.store, price=Decimal("9.99"), url="https://example.test/game"
        )

        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(PriceRecord.objects.count(), 1)

    def test_changed_price_creates_a_new_history_point(self):
        record_snapshot(game=self.game, store=self.store, price="9.99")
        _, created = record_snapshot(game=self.game, store=self.store, price="7.99")
        self.assertTrue(created)
        self.assertEqual(PriceRecord.objects.count(), 2)

    def test_invalid_price_is_rejected_before_it_reaches_database(self):
        for value in (None, "not-a-number", "NaN", "Infinity", "-1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                record_snapshot(game=self.game, store=self.store, price=value)

        self.assertFalse(PriceRecord.objects.exists())

    def test_untrusted_discount_is_clamped(self):
        record, created = record_snapshot(
            game=self.game, store=self.store, price="9.99", discount_percent="700.2"
        )

        self.assertTrue(created)
        self.assertEqual(record.discount_percent, 100)

    def test_long_retailer_url_is_not_truncated_at_legacy_default(self):
        url = "https://retailer.example/search?redirect=" + ("a" * 500)
        record, _ = record_snapshot(
            game=self.game, store=self.store, price="9.99", url=url
        )

        self.assertEqual(record.url, url)
