"""Historical price insight calculations stay truthful and deterministic."""

from datetime import datetime, timedelta, timezone as dt_timezone

from django.test import SimpleTestCase

from apps.games.price_insights import build_price_insights
from apps.games.prediction import predict_deal
from apps.games.models import Game


class PriceInsightTests(SimpleTestCase):
    def test_uses_daily_market_lows_and_labels_a_recorded_low(self):
        now = datetime(2026, 9, 2, 12, tzinfo=dt_timezone.utc)
        timestamps = [
            (now - timedelta(days=2)).isoformat(),
            (now - timedelta(days=1)).isoformat(),
            now.isoformat(),
        ]
        chart = {
            "timestamps": timestamps,
            "best": [30, 20, 10],
            "series": {"Steam": [30, 20, 10], "GOG": [None, 25, 15]},
            "observed": {"Steam": [True, True, True], "GOG": [False, True, True]},
            "sellers": ["Steam", "GOG"],
            "snapshot_count": 6,
        }

        insight = build_price_insights(chart, now=now)

        self.assertTrue(insight["has_data"])
        self.assertEqual(insight["current"], 10)
        self.assertEqual(insight["recorded_low"], 10)
        self.assertEqual(insight["typical"], 20)
        self.assertEqual(insight["vs_typical_percent"], 50)
        self.assertEqual(insight["verdict"], "Lowest shown")
        self.assertEqual(insight["confidence"], "Medium")

    def test_multiple_checks_on_one_day_count_as_one_market_sample(self):
        now = datetime(2026, 9, 2, 18, tzinfo=dt_timezone.utc)
        timestamps = [
            (now - timedelta(days=1)).isoformat(),
            now.replace(hour=9).isoformat(),
            now.isoformat(),
        ]
        chart = {
            "timestamps": timestamps,
            "best": [50, 100, 1],
            "series": {"Shop": [50, 100, 1]},
            "observed": {"Shop": [True, True, True]},
            "sellers": ["Shop"],
            "snapshot_count": 3,
        }

        insight = build_price_insights(chart, now=now)

        self.assertEqual(insight["day_count"], 2)
        self.assertEqual(insight["typical"], 25.5)

    def test_stale_quote_is_not_presented_as_current_insight(self):
        now = datetime(2026, 9, 2, 12, tzinfo=dt_timezone.utc)
        old = (now - timedelta(days=8)).isoformat()
        chart = {
            "timestamps": [old],
            "best": [9.99],
            "series": {"Old shop": [9.99]},
            "observed": {"Old shop": [True]},
        }

        self.assertEqual(build_price_insights(chart, now=now), {"has_data": False})

    def test_current_uses_each_sellers_latest_real_check_not_carried_value(self):
        now = datetime(2026, 9, 2, 12, tzinfo=dt_timezone.utc)
        chart = {
            "timestamps": [(now - timedelta(days=8)).isoformat(), now.isoformat()],
            "best": [5, 5],
            "series": {"Old cheap": [5, 5], "Checked today": [None, 100]},
            "observed": {"Old cheap": [True, False], "Checked today": [False, True]},
            "sellers": ["Old cheap", "Checked today"],
            "snapshot_count": 2,
        }

        insight = build_price_insights(chart, now=now)

        self.assertEqual(insight["current"], 100)

    def test_sold_out_tombstone_removes_seller_from_current_candidates(self):
        now = datetime(2026, 9, 2, 12, tzinfo=dt_timezone.utc)
        chart = {
            "timestamps": [(now - timedelta(days=1)).isoformat(), now.isoformat()],
            "best": [10, None],
            "series": {"Shop": [10, None]},
            "observed": {"Shop": [True, True]},
            "sellers": ["Shop"],
        }

        self.assertEqual(build_price_insights(chart, now=now), {"has_data": False})

    def test_free_price_does_not_divide_by_zero(self):
        now = datetime(2026, 9, 2, 12, tzinfo=dt_timezone.utc)
        chart = {
            "timestamps": [now.isoformat()],
            "best": [0],
            "series": {"Steam": [0]},
            "observed": {"Steam": [True]},
            "sellers": ["Steam"],
        }

        insight = build_price_insights(chart, now=now)

        self.assertEqual(insight["verdict"], "Free now")
        self.assertIsNone(insight["vs_typical_percent"])

    def test_deal_outlook_reuses_insight_without_a_database_query(self):
        prediction = predict_deal(
            game=Game(title="Unsaved proves no query"),
            best_offer_gbp=10,
            price_insights={"has_data": True, "vs_typical_percent": 25},
        )

        self.assertIn("25% below the recorded median", " ".join(prediction["signals"]))

    def test_deal_outlook_keeps_a_valid_free_best_offer(self):
        prediction = predict_deal(
            steam_price_gbp=20,
            best_offer_gbp=0,
            launch_gbp=40,
            price_insights={"has_data": True, "vs_typical_percent": 100},
        )

        self.assertEqual(prediction["under_launch_pct"], 100)
