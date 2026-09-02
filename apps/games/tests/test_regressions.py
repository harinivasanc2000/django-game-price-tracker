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
from apps.games.views import _build_chart_payload


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

    @patch("apps.games.tasks.platform_bundle")
    @patch("apps.games.tasks.deals_for_title")
    @patch("apps.games.tasks.get_app_details")
    def test_refresh_does_not_save_unknown_steam_price(
        self, get_detail, deals, bundle
    ):
        game = Game.objects.create(
            title="Unpriced game", slug="unpriced-game", platform=Game.Platform.PC, steam_app_id=self.app_id
        )
        get_detail.return_value = self.unknown_detail
        deals.return_value = []
        bundle.return_value = {}

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

    def test_chart_orders_history_before_the_live_now_point(self):
        """Store insertion order must not scramble a multi-seller time series."""
        game = Game.objects.create(title="Charted", slug="charted", platform=Game.Platform.PC)
        steam = Store.objects.create(name="Steam", slug="steam")
        record = PriceRecord.objects.create(game=game, store=steam, price=Decimal("20.00"))
        PriceRecord.objects.filter(pk=record.pk).update(recorded_at=timezone.now() - timedelta(days=1))

        chart = _build_chart_payload(
            game,
            {"price": Decimal("10.00"), "currency": "GBP", "price_status": "paid"},
            [],
            None,
            [], [], [], [],
        )

        self.assertEqual(chart["labels"][-1], "Now")
        self.assertEqual(chart["series"]["Steam"], [20.0, 10.0])

    def test_chart_without_prices_is_not_marked_as_drawable(self):
        chart = _build_chart_payload(None, {}, [], None, [], [], [], [])
        self.assertFalse(chart["has_data"])

    def test_chart_aligns_sellers_with_asynchronous_refresh_times(self):
        """A market line must compare last-known quotes, not one refresh at a time."""
        game = Game.objects.create(title="Aligned", slug="aligned", platform=Game.Platform.PC)
        steam = Store.objects.create(name="Steam", slug="aligned-steam")
        cex = Store.objects.create(name="CeX", slug="aligned-cex")
        now = timezone.now()
        steam_old = PriceRecord.objects.create(game=game, store=steam, price=Decimal("20.00"))
        cex_record = PriceRecord.objects.create(game=game, store=cex, price=Decimal("15.00"))
        steam_new = PriceRecord.objects.create(game=game, store=steam, price=Decimal("10.00"))
        PriceRecord.objects.filter(pk=steam_old.pk).update(recorded_at=now - timedelta(days=3))
        PriceRecord.objects.filter(pk=cex_record.pk).update(recorded_at=now - timedelta(days=2))
        PriceRecord.objects.filter(pk=steam_new.pk).update(recorded_at=now - timedelta(days=1))

        chart = _build_chart_payload(game, {}, [], None, [], [], [], [])

        self.assertEqual(chart["series"]["Steam"], [20.0, 20.0, 10.0])
        self.assertEqual(chart["series"]["CeX"], [None, 15.0, 15.0])
        self.assertEqual(chart["observed"]["Steam"], [True, False, True])
        self.assertEqual(chart["average"], [20.0, 17.5, 12.5])
        self.assertEqual(chart["best"], [20.0, 15.0, 10.0])

    def test_chart_uses_cheapest_same_store_live_row_and_includes_free_games(self):
        chart = _build_chart_payload(
            None,
            {"price": Decimal("0.00"), "currency": "GBP", "price_status": "free"},
            [],
            None,
            [], [], [], [],
            live_store_rows=[
                (
                    "GAME UK",
                    [
                        {"price": Decimal("29.99"), "currency": "GBP"},
                        {"price": Decimal("19.99"), "currency": "GBP"},
                    ],
                    "GBP",
                )
            ],
        )

        self.assertTrue(chart["has_data"])
        self.assertEqual(chart["series"]["Steam"], [0.0])
        self.assertEqual(chart["series"]["GAME UK"], [19.99])
        self.assertEqual(chart["best"], [0.0])

    def test_chart_does_not_carry_stale_quotes_into_a_newer_market_average(self):
        game = Game.objects.create(title="Freshness", slug="freshness", platform=Game.Platform.PC)
        old_store = Store.objects.create(name="Old quote", slug="old-quote")
        fresh_store = Store.objects.create(name="Fresh quote", slug="fresh-quote")
        old = PriceRecord.objects.create(game=game, store=old_store, price=Decimal("5.00"))
        fresh = PriceRecord.objects.create(game=game, store=fresh_store, price=Decimal("25.00"))
        PriceRecord.objects.filter(pk=old.pk).update(recorded_at=timezone.now() - timedelta(days=10))
        PriceRecord.objects.filter(pk=fresh.pk).update(recorded_at=timezone.now())

        chart = _build_chart_payload(game, {}, [], None, [], [], [], [])

        self.assertEqual(chart["series"]["Old quote"], [5.0, None, None])
        self.assertEqual(chart["average"], [5.0, None, 25.0])
        self.assertEqual(chart["best"], [5.0, None, 25.0])

    def test_chart_keeps_flat_price_fresh_when_daily_checks_continue(self):
        game = Game.objects.create(title="Heartbeat", slug="heartbeat", platform=Game.Platform.PC)
        store = Store.objects.create(name="Daily shop", slug="daily-shop")
        now = timezone.now()
        records = [
            PriceRecord.objects.create(game=game, store=store, price=Decimal("12.00"))
            for _ in range(11)
        ]
        for days_ago, record in zip(range(10, -1, -1), records):
            PriceRecord.objects.filter(pk=record.pk).update(
                recorded_at=now - timedelta(days=days_ago)
            )

        chart = _build_chart_payload(game, {}, [], None, [], [], [], [])

        self.assertTrue(chart["series"]["Daily shop"])
        self.assertNotIn(None, chart["series"]["Daily shop"])

    def test_chart_ignores_explicitly_unavailable_history_and_live_rows(self):
        game = Game.objects.create(title="Unavailable", slug="unavailable", platform=Game.Platform.PC)
        store = Store.objects.create(name="Sold out shop", slug="sold-out-shop")
        PriceRecord.objects.create(
            game=game,
            store=store,
            price=Decimal("1.00"),
            in_stock=False,
        )

        chart = _build_chart_payload(
            game,
            {"price": Decimal("0"), "price_status": "free", "in_stock": False},
            [],
            None,
            [], [], [], [],
            live_store_rows=[
                ("Sold out live", [{"price": Decimal("2"), "in_stock": False}], "GBP")
            ],
        )

        self.assertFalse(chart["has_data"])
        self.assertNotIn("Sold out shop", chart["sellers"])

    def test_sold_out_snapshot_ends_an_older_graph_quote(self):
        game = Game.objects.create(title="Ended quote", slug="ended-quote")
        store = Store.objects.create(name="Tombstone shop", slug="tombstone-shop")
        available = PriceRecord.objects.create(
            game=game, store=store, price=Decimal("12.00"), in_stock=True
        )
        unavailable = PriceRecord.objects.create(
            game=game, store=store, price=Decimal("12.00"), in_stock=False
        )
        PriceRecord.objects.filter(pk=available.pk).update(
            recorded_at=timezone.now() - timedelta(days=1)
        )

        chart = _build_chart_payload(game, {}, [], None, [], [], [], [])

        self.assertEqual(chart["series"]["Tombstone shop"], [12.0, None])
        self.assertEqual(chart["observed"]["Tombstone shop"], [True, True])
        self.assertIsNone(chart["latest_best"])

    def test_compare_uses_latest_in_stock_offer_per_store(self):
        game = Game.objects.create(title="Current only", slug="current-only", platform=Game.Platform.PS5)
        first_store = Store.objects.create(name="First", slug="current-first")
        second_store = Store.objects.create(name="Second", slug="current-second")
        sold_out_store = Store.objects.create(name="Unavailable", slug="current-unavailable")
        old = PriceRecord.objects.create(game=game, store=first_store, price=Decimal("5.00"))
        current = PriceRecord.objects.create(game=game, store=first_store, price=Decimal("20.00"))
        best = PriceRecord.objects.create(game=game, store=second_store, price=Decimal("10.00"))
        PriceRecord.objects.create(
            game=game, store=sold_out_store, price=Decimal("1.00"), in_stock=False
        )
        PriceRecord.objects.filter(pk=old.pk).update(
            recorded_at=timezone.now() - timedelta(days=2)
        )

        response = self.client.get(reverse("games:compare", args=[game.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["lowest"].pk, best.pk)
        self.assertEqual({row.pk for row in response.context["prices"]}, {current.pk, best.pk})

    def test_non_steam_compare_page_renders_safe_graph_payload(self):
        game = Game.objects.create(title="Console chart", slug="console-chart", platform=Game.Platform.PS5)
        store = Store.objects.create(name="Bad </script><script>alert(1)</script>", slug="safe-chart-store")
        PriceRecord.objects.create(game=game, store=store, price=Decimal("39.99"))

        response = self.client.get(reverse("games:compare", args=[game.slug]))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="priceChart"')
        self.assertContains(response, 'id="price-chart-data"')
        self.assertNotIn("</script><script>alert(1)</script>", content)
        self.assertIn(r"Bad \u003C/script\u003E\u003Cscript\u003Ealert(1)\u003C/script\u003E", content)


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
        exported = response.json()["games"][0]
        self.assertEqual(exported["latest"]["price"], "10.00")
        self.assertEqual(len(exported["current_offers"]), 1)
        self.assertEqual(exported["current_offers"][0]["price"], "10.00")
