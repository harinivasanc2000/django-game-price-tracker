"""Current-price selection tests for the best-deals page."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.games.models import Game, PriceRecord, Store


class BestDealsTests(TestCase):
    @patch("apps.games.views_best_deals.steam_featured", return_value={"specials": []})
    @patch("apps.games.views_best_deals.cheapshark_top_deals", return_value=[])
    def test_uses_lowest_current_store_price_not_newest_history_row(self, _cheapshark, _steam):
        """An old sale must not win, and a recent expensive store must not hide a deal."""
        game = Game.objects.create(title="Example", slug="example", platform=Game.Platform.PC)
        steam = Store.objects.create(name="Steam", slug="steam")
        gog = Store.objects.create(name="GOG", slug="gog")
        old_sale = PriceRecord.objects.create(game=game, store=steam, price=Decimal("5.00"))
        current_steam = PriceRecord.objects.create(game=game, store=steam, price=Decimal("15.00"))
        current_gog = PriceRecord.objects.create(game=game, store=gog, price=Decimal("20.00"))
        PriceRecord.objects.filter(pk=old_sale.pk).update(recorded_at=timezone.now() - timedelta(days=1))
        PriceRecord.objects.filter(pk=current_steam.pk).update(recorded_at=timezone.now() - timedelta(minutes=2))
        PriceRecord.objects.filter(pk=current_gog.pk).update(recorded_at=timezone.now() - timedelta(minutes=1))

        response = self.client.get("/deals/")

        self.assertEqual(response.status_code, 200)
        rows = response.context["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["store"], "Steam")
        self.assertEqual(rows[0]["price_gbp"], Decimal("15.00"))
