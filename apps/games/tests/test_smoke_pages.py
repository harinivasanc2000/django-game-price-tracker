"""Fast offline smoke coverage for every public top-level page."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse


class PublicPageSmokeTests(TestCase):
    @patch("apps.games.home_view._build_home_payload")
    @patch("apps.games.views_best_deals.cheapshark_top_deals", return_value=[])
    @patch("apps.games.views_best_deals.steam_featured", return_value={"specials": []})
    @patch("apps.games.buy_guide_view.buy_recommendations", return_value={})
    def test_public_pages_render_without_external_network(
        self, _guide, _steam, _cheapshark, home_payload
    ):
        cache.clear()
        home_payload.return_value = {
            "popular_cards": [],
            "hot_deals": [],
            "public_specials": [],
            "seasonal_window_days": 90,
        }
        urls = (
            reverse("games:home"),
            reverse("games:steam_search"),
            reverse("games:best_deals"),
            reverse("games:buy_guide"),
            reverse("games:research"),
            reverse("games:about"),
            reverse("games:appearance"),
            reverse("games:history"),
            reverse("games:health"),
            reverse("games:export_tracked"),
            reverse("games:export_training_csv"),
        )

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
