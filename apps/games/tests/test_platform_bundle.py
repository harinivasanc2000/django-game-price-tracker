"""The platform API must expose every UK source returned by the scraper bundle."""

from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.games.platform_bundle import (
    _bundle_cache_key,
    _filter_psn_generation,
    platform_bundle,
)


class PlatformBundleTests(SimpleTestCase):
    def tearDown(self):
        cache.clear()

    def test_cache_key_is_short_and_backend_safe(self):
        key = _bundle_cache_key("Pokémon: Scarlet & Violet", "switch", "10", "40", "new")
        self.assertLess(len(key), 50)
        self.assertNotIn(" ", key)
        self.assertNotIn("Pokémon", key)

    def test_playstation_generation_filter_drops_only_explicit_mismatches(self):
        rows = [
            {"name": "PS4 edition", "platforms": ["PS4"]},
            {"name": "PS5 edition", "platforms": ["PlayStation 5"]},
            {"name": "Cross-gen edition", "platforms": ["PS4", "PS5"]},
            {"name": "Metadata unavailable", "platforms": []},
        ]

        ps4 = _filter_psn_generation(rows, "ps4")
        ps5 = _filter_psn_generation(rows, "ps5")

        self.assertEqual(
            [row["name"] for row in ps4],
            ["PS4 edition", "Cross-gen edition", "Metadata unavailable"],
        )
        self.assertEqual(
            [row["name"] for row in ps5],
            ["PS5 edition", "Cross-gen edition", "Metadata unavailable"],
        )

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

    @patch("apps.games.platform_bundle.search_amazon_uk")
    @patch("apps.games.platform_bundle.fetch_uk_physical_bundle")
    def test_reversed_bounds_are_swapped_and_require_known_in_range_prices(
        self, fetch_uk, amazon
    ):
        fetch_uk.return_value = {"stores_total": 11, "uk_links": []}
        amazon.return_value = {
            "results": [
                {"name": "Unknown", "price": None},
                {"name": "Free", "price": Decimal("0")},
                {"name": "In range", "price": Decimal("15")},
                {"name": "Too high", "price": Decimal("25")},
            ],
            "blocked": False,
            "search_url": "https://www.amazon.co.uk/s?k=bounds",
        }

        payload = platform_bundle(
            "Bounds regression unique",
            "pc",
            min_price=Decimal("20"),
            max_price=Decimal("10"),
            condition="invalid-condition",
        )

        self.assertEqual([row["name"] for row in payload["amazon_rows"]], ["In range"])
        self.assertEqual(payload["active_filters"]["min_price"], "10")
        self.assertEqual(payload["active_filters"]["max_price"], "20")
        self.assertEqual(payload["active_filters"]["condition"], "")
