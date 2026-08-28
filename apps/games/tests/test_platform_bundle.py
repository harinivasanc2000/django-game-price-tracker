"""The platform API must expose every UK source returned by the scraper bundle."""

from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.games.platform_bundle import _bundle_cache_key, platform_bundle


class PlatformBundleTests(SimpleTestCase):
    def tearDown(self):
        cache.clear()

    def test_cache_key_is_short_and_backend_safe(self):
        key = _bundle_cache_key("Pokémon: Scarlet & Violet", "switch", "10", "40", "new")
        self.assertLess(len(key), 50)
        self.assertNotIn(" ", key)
        self.assertNotIn("Pokémon", key)

    @patch("apps.games.platform_bundle.search_amazon_uk")
    @patch("apps.games.platform_bundle.fetch_uk_physical_bundle")
    def test_specialist_sources_are_serialised_for_page_and_ajax(self, fetch_uk, amazon):
        cache.clear()
        amazon.return_value = {"results": [], "blocked": True, "search_url": ""}
        fetch_uk.return_value = {
            "the_game_collection": {
                "results": [
                    {
                        "name": "Example game PS5",
                        "price": Decimal("19.99"),
                        "currency": "GBP",
                        "url": "https://www.thegamecollection.net/products/example",
                    }
                ],
                "blocked": False,
                "search_url": "https://www.thegamecollection.net/search?q=example",
            },
            "stores_ok": 1,
            "stores_total": 11,
            "uk_links": [],
        }

        payload = platform_bundle("Example game", "pc")

        specialist = payload["specialist_sources"][0]
        self.assertEqual(specialist["label"], "The Game Collection")
        self.assertEqual(specialist["rows"][0]["price"], 19.99)
        self.assertEqual(payload["stores_total"], 11)
