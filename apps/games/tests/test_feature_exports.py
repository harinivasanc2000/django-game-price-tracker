"""Per-game exports are bounded, isolated, and spreadsheet-safe."""

import csv
from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.games.models import Game, PriceRecord, Store


class GameHistoryExportTests(TestCase):
    def setUp(self):
        self.game = Game.objects.create(title="Export me", slug="export-me")
        self.other = Game.objects.create(title="Not me", slug="not-me")
        self.store = Store.objects.create(name="=Formula Shop", slug="formula-shop")
        self.old = PriceRecord.objects.create(
            game=self.game, store=self.store, price=Decimal("20.00")
        )
        self.new = PriceRecord.objects.create(
            game=self.game, store=self.store, price=Decimal("10.00")
        )
        PriceRecord.objects.filter(pk=self.old.pk).update(
            recorded_at=timezone.now() - timedelta(days=1)
        )
        PriceRecord.objects.create(game=self.other, store=self.store, price=Decimal("1.00"))
        self.url = reverse("games:export_game_prices", args=[self.game.slug])

    @staticmethod
    def _rows(response):
        body = b"".join(response.streaming_content).decode("utf-8")
        return list(csv.reader(StringIO(body)))

    def test_streams_only_requested_game_newest_first(self):
        response = self.client.get(self.url)
        rows = self._rows(response)

        self.assertEqual(response.status_code, 200)
        self.assertIn("export-me-price-history.csv", response["Content-Disposition"])
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1][1], "Export me")
        self.assertEqual(rows[1][5], "10.00")
        self.assertEqual(rows[2][5], "20.00")
        self.assertEqual(rows[1][3], "'=Formula Shop")
        self.assertNotIn("Not me", str(rows))

    def test_limit_is_bounded_and_invalid_value_soft_falls_back(self):
        limited = self._rows(self.client.get(f"{self.url}?limit=1"))
        fallback = self._rows(self.client.get(f"{self.url}?limit=invalid"))

        self.assertEqual(len(limited), 2)
        self.assertEqual(len(fallback), 3)

    def test_inactive_or_unknown_game_is_not_exported(self):
        self.game.is_active = False
        self.game.save(update_fields=["is_active", "updated_at"])

        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(
            self.client.get(reverse("games:export_game_prices", args=["missing"])).status_code,
            404,
        )
