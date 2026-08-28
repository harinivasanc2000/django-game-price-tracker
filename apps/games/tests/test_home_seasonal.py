"""Seasonal home-page ranking is based on observed sale activity, not claims."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.games.home_view import _seasonal_app_ids
from apps.games.models import Game, PriceRecord, Store


class SeasonalHomeTests(TestCase):
    def test_recent_discount_frequency_ranks_before_current_specials(self):
        store = Store.objects.create(name="Steam", slug="steam")
        frequent = Game.objects.create(title="Frequent", slug="frequent", steam_app_id=101)
        occasional = Game.objects.create(title="Occasional", slug="occasional", steam_app_id=202)
        for days_ago in (2, 12):
            price = PriceRecord.objects.create(
                game=frequent, store=store, price=Decimal("10.00"), discount_percent=50
            )
            PriceRecord.objects.filter(pk=price.pk).update(recorded_at=timezone.now() - timedelta(days=days_ago))
        price = PriceRecord.objects.create(
            game=occasional, store=store, price=Decimal("12.00"), discount_percent=25
        )
        PriceRecord.objects.filter(pk=price.pk).update(recorded_at=timezone.now() - timedelta(days=3))

        app_ids, sources = _seasonal_app_ids([{"app_id": 303}])

        self.assertEqual(app_ids[:3], [101, 202, 303])
        self.assertEqual(sources[101], "90-day price-drop history")
        self.assertEqual(sources[303], "Steam special right now")
