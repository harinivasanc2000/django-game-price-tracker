"""The watch dashboard reuses current snapshots and supports inline targets."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.games.models import Game, PriceAlert, PriceRecord, Store, Watch
from apps.games.tasks import _check_watch_targets


class WatchDashboardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="dashboard-player", password="safe-password"
        )
        self.game = Game.objects.create(title="Watched game", slug="watched-dashboard")
        self.watch = Watch.objects.create(
            user=self.user, game=self.game, target_price=Decimal("12.00")
        )
        self.store = Store.objects.create(name="Current shop", slug="current-shop")
        self.client.force_login(self.user)

    def test_profile_shows_cheapest_fresh_offer_and_target_gap(self):
        PriceRecord.objects.create(game=self.game, store=self.store, price=Decimal("15.00"))
        sold_out = Store.objects.create(name="Sold out", slug="sold-out-dashboard")
        PriceRecord.objects.create(
            game=self.game, store=sold_out, price=Decimal("1.00"), in_stock=False
        )

        response = self.client.get(reverse("games:profile"))
        shown = response.context["watches"][0]

        self.assertEqual(shown.current_price_gbp, Decimal("15.00"))
        self.assertEqual(shown.target_gap, Decimal("3.00"))
        self.assertContains(response, "£3.00 above target")

    def test_inline_target_update_returns_to_profile(self):
        response = self.client.post(
            reverse("games:watch", args=[self.game.slug]),
            {"target_price": "9.50", "next": "profile"},
        )

        self.assertRedirects(response, reverse("games:profile"))
        self.watch.refresh_from_db()
        self.assertEqual(self.watch.target_price, Decimal("9.50"))

    def test_inline_unwatch_returns_to_profile(self):
        response = self.client.post(
            reverse("games:unwatch", args=[self.game.slug]), {"next": "profile"}
        )

        self.assertRedirects(response, reverse("games:profile"))
        self.assertFalse(Watch.objects.filter(pk=self.watch.pk).exists())

    def test_verified_free_offer_can_trigger_zero_target(self):
        self.watch.target_price = Decimal("0")
        self.watch.save(update_fields=["target_price"])

        created = _check_watch_targets(self.game, Decimal("0"), "GBP", "Steam")

        self.assertEqual(created, 1)
        self.assertTrue(PriceAlert.objects.filter(watch=self.watch, price=0).exists())

    def test_aging_quote_warns_before_hard_expiry(self):
        record = PriceRecord.objects.create(
            game=self.game, store=self.store, price=Decimal("11.00")
        )
        aging_at = timezone.now() - timedelta(days=2)
        PriceRecord.objects.filter(pk=record.pk).update(
            recorded_at=aging_at,
            last_checked_at=aging_at,
        )

        response = self.client.get(reverse("games:compare", args=[self.game.slug]))

        self.assertContains(response, "Needs refresh")
        self.assertContains(response, "<time datetime=", html=False)
