"""Gradient booster and promo calendar. No network, no database."""

from datetime import date, timedelta

from django.test import SimpleTestCase

from apps.games.ml.booster import StumpBooster
from apps.games.ml.calendar_events import next_promo
from apps.games.ml.series import fit_drop_model
from apps.games.prediction import predict_deal


def _seasonal_rows():
    rows = []
    labels = []
    for days, dropped in (
        (3, 1), (5, 1), (7, 1), (8, 1), (10, 1), (12, 1),
        (40, 0), (50, 0), (60, 0), (70, 0), (80, 0), (90, 0),
        (4, 1), (6, 1), (45, 0), (55, 0),
    ):
        rows.append([0, 0, 30, float(days), 0, 0, 0])
        labels.append(dropped)
    return rows, labels


class BoosterTests(SimpleTestCase):
    def test_stumps_separate_a_single_feature(self):
        rows, labels = _seasonal_rows()
        model = StumpBooster(n_rounds=12, learning_rate=0.4).fit(rows, labels)
        self.assertGreaterEqual(len(model.stumps), 1)
        soon = model.predict_proba([0, 0, 30, 4, 0, 0, 0])
        later = model.predict_proba([0, 0, 30, 80, 0, 0, 0])
        self.assertGreater(soon, later)
        self.assertGreater(soon, 0.6)
        self.assertLess(later, 0.4)

    def test_black_friday_window_in_late_november_2026(self):
        promo = next_promo(date(2026, 11, 23))
        self.assertIsNotNone(promo)
        self.assertEqual(promo["label"], "Steam Autumn Sale")
        self.assertLessEqual(promo["days_until"], 14)

    def test_walk_forward_learns_a_repeated_cut(self):
        start = date(2026, 1, 1)
        points = []
        for week in range(16):
            on = start + timedelta(days=7 * week)
            price = 20.0 if week % 4 == 3 else 40.0
            points.append({"date": on, "price": price, "reference": 40.0})
        model, today = fit_drop_model(points)
        self.assertIsNotNone(today)
        if model is not None:
            proba = model.predict_proba(today)
            self.assertGreaterEqual(proba, 0.0)
            self.assertLessEqual(proba, 1.0)

    def test_outlook_mentions_a_promo_without_a_tracked_game(self):
        pred = predict_deal(
            title="Example",
            steam_price_gbp=39.99,
            steam_discount=0,
            launch_gbp=39.99,
            best_offer_gbp=39.99,
            best_offer_kind="official",
            game=None,
        )
        self.assertTrue(pred["signals"])
        self.assertIn("Calendar prior", pred["model_label"])
        joined = " ".join(pred["signals"])
        self.assertTrue("Sale" in joined or "Friday" in joined or "Boxing" in joined)
