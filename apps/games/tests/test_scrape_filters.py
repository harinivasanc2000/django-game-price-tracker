"""Unit tests for public scrape filters (no network)."""

from decimal import Decimal

from django.test import SimpleTestCase

from apps.games.clients.scrape_filters import (
    filter_product_rows,
    parse_price_bound,
    detect_condition,
)
from apps.games.clients.uk_stores import _ebay_search_url


class ScrapeFilterTests(SimpleTestCase):
    def test_price_bounds(self):
        self.assertEqual(parse_price_bound("12.50"), Decimal("12.50"))
        self.assertIsNone(parse_price_bound(""))
        self.assertIsNone(parse_price_bound("abc"))

    def test_condition_detection(self):
        self.assertEqual(detect_condition("Halo Infinite Pre-Owned"), "used")
        self.assertEqual(detect_condition("Halo Infinite Brand New Sealed"), "new")

    def test_max_price_and_used(self):
        rows = [
            {"name": "God of War PS5", "price": 15, "is_used": True},
            {"name": "God of War PS5", "price": 40, "is_used": False},
            {"name": "DualSense Controller", "price": 50},
        ]
        out = filter_product_rows(
            rows,
            title="God of War",
            platform="ps5",
            max_price=Decimal("20"),
            condition="used",
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["price"], 15)

    def test_ebay_url_includes_public_filters(self):
        url = _ebay_search_url(
            "Elden Ring",
            "ps5",
            min_price=Decimal("10"),
            max_price=Decimal("35"),
            condition="used",
        )
        self.assertIn("LH_BIN=1", url)
        self.assertIn("_udlo=10", url)
        self.assertIn("_udhi=35", url)
        self.assertIn("LH_ItemCondition=3000", url)
        self.assertIn("PS5", url)
