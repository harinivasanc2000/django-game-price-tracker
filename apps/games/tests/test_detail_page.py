"""Main comparison-page rendering tests without depending on live retailers."""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.games.detail_helpers import empty_platform_bundle


class SteamDetailPageTests(TestCase):
    @patch("apps.games.views_steam_detail.similar_steam_titles", return_value=[])
    @patch("apps.games.views_steam_detail.deals_for_title")
    @patch("apps.games.views_steam_detail.steam_news", return_value=[])
    @patch("apps.games.views_steam_detail.platform_bundle")
    @patch("apps.games.views_steam_detail.get_app_details")
    def test_main_deal_links_render_as_real_outbound_urls(
        self, get_detail, platform, _news, deals, _similar
    ):
        app_id = 12345
        get_detail.return_value = {
            "app_id": app_id,
            "name": "Example game",
            "type": "game",
            "genres": [],
            "platforms": ["windows"],
            "price": Decimal("9.99"),
            "currency": "GBP",
            "price_status": "paid",
            "discount": 0,
            "url": "https://store.steampowered.com/app/12345/",
            "header_image": "",
            "screenshots": [],
        }
        bundle = empty_platform_bundle("Example game")
        bundle["specialist_sources"] = [
            {
                "key": "shopto",
                "label": "ShopTo",
                "rows": [
                    {
                        "name": "Example game PS5",
                        "price": Decimal("12.99"),
                        "currency": "GBP",
                        "url": "https://www.shopto.net/en/example-game/",
                    }
                ],
                "blocked": False,
                "search_url": "https://www.shopto.net/en/search/?input_search=Example+game",
            }
        ]
        bundle["stores_ok"] = 1
        platform.return_value = bundle
        deals.return_value = [
            {
                "store_name": "Fanatical",
                "price": Decimal("7.99"),
                "currency": "USD",
                "url": "https://www.cheapshark.com/redirect?dealID=example",
            }
        ]

        response = self.client.get(reverse("games:steam_detail", args=[app_id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="https://store.steampowered.com/app/12345/"')
        self.assertContains(response, 'href="https://www.cheapshark.com/redirect?dealID=example"')
        self.assertContains(response, 'href="https://www.shopto.net/en/example-game/"')
        self.assertIn("ShopTo", [offer["store"] for offer in response.context["live_offers"]])
