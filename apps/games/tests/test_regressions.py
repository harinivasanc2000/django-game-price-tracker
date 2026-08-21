"""Tests for behaviour that must stay safe when upstream store data is incomplete."""

from unittest.mock import patch
from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.games.models import Game, PriceRecord, Store
from apps.games.tasks import refresh_one_game


class TrackingRegressionTests(TestCase):
    """Tracking changes data, so it must be POST-only and price-aware."""

    def setUp(self):
        self.app_id = 12345
        self.url = reverse("games:track_steam", args=[self.app_id])
        self.unknown_detail = {
            "name": "Unpriced game",
            "header_image": "",
            "price_status": "unknown",
            "price": None,
            "currency": "GBP",
            "url": "https://store.steampowered.com/app/12345/",
        }

    def test_tracking_rejects_get_requests(self):
        """Links and crawlers cannot silently add tracked games."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
        self.assertFalse(Game.objects.exists())

    @patch("apps.games.views.ensure_uk_stores")
    @patch("apps.games.views.get_app_details")
    @patch("apps.games.tasks.refresh_single_game.delay")
    def test_unknown_price_tracks_game_without_a_fake_zero_snapshot(
        self, delay, get_detail, ensure_stores
    ):
        get_detail.return_value = self.unknown_detail
        response = self.client.post(self.url)

        # Do not follow the redirect: the detail page is independently backed by Steam.
        self.assertRedirects(
            response,
            reverse("games:steam_detail", args=[self.app_id]),
            fetch_redirect_response=False,
        )
        self.assertTrue(Game.objects.filter(steam_app_id=self.app_id, is_active=True).exists())
        self.assertFalse(PriceRecord.objects.exists())
        delay.assert_called_once()

    @patch("apps.games.tasks.search_amazon_uk")
    @patch("apps.games.tasks.best_psn_deal")
    @patch("apps.games.tasks.deals_for_title")
    @patch("apps.games.tasks.get_app_details")
    def test_refresh_does_not_save_unknown_steam_price(
        self, get_detail, deals, psn, amazon
    ):
        game = Game.objects.create(
            title="Unpriced game", slug="unpriced-game", platform=Game.Platform.PC, steam_app_id=self.app_id
        )
        get_detail.return_value = self.unknown_detail
        deals.return_value = []
        psn.return_value = None
        amazon.return_value = {"results": []}

        result = refresh_one_game(game)

        self.assertFalse(result["steam"])
        self.assertIn("steam price unavailable", result["errors"])
        self.assertFalse(PriceRecord.objects.exists())

    def test_watch_rejects_non_finite_target_price(self):
        """NaN and Infinity should return a validation message, never a database error."""
        user = get_user_model().objects.create_user(username="player", password="safe-password")
        game = Game.objects.create(title="Watched", slug="watched", platform=Game.Platform.PC)
        self.client.force_login(user)

        response = self.client.post(reverse("games:watch", args=[game.slug]), {"target_price": "NaN"})

        self.assertRedirects(response, reverse("games:compare", args=[game.slug]), fetch_redirect_response=False)


class ExportRegressionTests(TestCase):
    """Exports are public endpoints and should be resilient to bad query strings."""

    def test_csv_export_accepts_invalid_and_negative_limits(self):
        url = reverse("games:export_training_csv")
        for limit in ("not-a-number", "-20", "0"):
            response = self.client.get(url, {"limit": limit})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")

    def test_json_export_uses_the_latest_snapshot_for_each_game(self):
        game = Game.objects.create(title="Exported", slug="exported", platform=Game.Platform.PC)
        store = Store.objects.create(name="Steam", slug="steam")
        old = PriceRecord.objects.create(game=game, store=store, price=Decimal("20.00"))
        newest = PriceRecord.objects.create(game=game, store=store, price=Decimal("10.00"))
        PriceRecord.objects.filter(pk=old.pk).update(recorded_at=timezone.now() - timedelta(days=1))
        PriceRecord.objects.filter(pk=newest.pk).update(recorded_at=timezone.now())

        response = self.client.get(reverse("games:export_tracked"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["games"][0]["latest"]["price"], "10.00")
