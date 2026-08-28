"""Accuracy rules shared by the polite BS4 UK retailer clients."""

from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.games.clients.scrape_utils import soup_from
from apps.games.clients.uk_stores import (
    _keep_matching_rows,
    _rows_from_cards,
    _title_matches,
    _try_specialist_uncached,
    merge_best_local,
    platform_query,
    uk_search_links,
)


class UKStoreMatchingTests(SimpleTestCase):
    def test_accepts_matching_game_title(self):
        self.assertTrue(_title_matches("Cyberpunk 2077 Ultimate Edition", "Cyberpunk 2077"))
        self.assertTrue(_title_matches("God of War Ragnarök PS5", "God of War Ragnarök"))

    def test_rejects_unrelated_accessory_cards(self):
        self.assertFalse(_title_matches("PlayStation 5 DualSense Controller", "Cyberpunk 2077"))
        self.assertFalse(_title_matches("Nintendo Switch Carry Case", "God of War"))
        self.assertFalse(_title_matches("Xbox Wireless Headset", "Halo Infinite"))

    def test_rejects_lego_when_query_is_arkham_knight(self):
        q = "Batman: Arkham Knight"
        self.assertFalse(_title_matches("LEGO Batman 3 Beyond Gotham", q))
        self.assertFalse(_title_matches("Batman Arkham Asylum", q))
        self.assertTrue(_title_matches("Batman Arkham Knight PS4", q))

    def test_empty_filtered_source_remains_a_clickable_search_fallback(self):
        source = {
            "results": [{"name": "Nintendo Switch Carry Case", "price": 10}],
            "blocked": False,
            "search_url": "https://example.test/search",
        }
        filtered = _keep_matching_rows(source, "God of War")
        self.assertEqual(filtered["results"], [])
        self.assertTrue(filtered["blocked"])
        self.assertEqual(filtered["search_url"], "https://example.test/search")

    def test_matching_rows_are_sorted_by_score_then_price(self):
        source = {
            "results": [
                {"name": "Halo Infinite", "price": 29.99},
                {"name": "Halo Infinite Standard", "price": 9.99},
                {"name": "Halo Infinite", "price": 19.99},
            ],
            "blocked": False,
            "search_url": "https://example.test/search",
        }
        filtered = _keep_matching_rows(source, "Halo Infinite")
        prices = [r["price"] for r in filtered["results"]]
        self.assertEqual(prices, [9.99, 19.99, 29.99])

    def test_platform_queries_cover_current_console_names(self):
        self.assertEqual(platform_query("Mario Kart World", "switch2"), "Mario Kart World Nintendo Switch 2")
        self.assertEqual(platform_query("Forza Horizon", "xbox-series-x"), "Forza Horizon Xbox Series X")

    def test_search_links_include_specialists_second_hand_and_comparison(self):
        links = uk_search_links(
            "Elden Ring", "ps5", min_price="50", max_price="10", condition="pre-owned"
        )
        by_name = {item["name"]: item["url"] for item in links}
        self.assertIn("The Game Collection", by_name)
        self.assertIn("Hit", by_name)
        self.assertIn("ShopTo", by_name)
        self.assertIn("SimplyGames", by_name)
        self.assertIn("Cash Converters", by_name)
        self.assertIn("Vinted", by_name)
        self.assertIn("PriceRunner UK", by_name)
        self.assertIn("_udlo=10", by_name["eBay UK"])
        self.assertIn("_udhi=50", by_name["eBay UK"])
        self.assertIn("LH_ItemCondition=3000", by_name["eBay UK"])

    def test_card_parser_uses_current_price_and_safe_direct_link(self):
        soup = soup_from(
            """
            <article class="card">
              <a href="https://attacker.test/fake">tracking</a>
              <a href="/products/halo-infinite"><h3>Halo Infinite Xbox Series X</h3></a>
              <span class="price">£19.95 RRP £49.99</span>
              <span>In stock</span>
            </article>
            """
        )
        rows = _rows_from_cards(
            soup,
            store_name="Hit",
            base_url="https://hit.co.uk/search?q=halo",
            selectors="article",
            limit=4,
            allowed_hosts=("hit.co.uk",),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["price"], Decimal("19.95"))
        self.assertEqual(rows[0]["url"], "https://hit.co.uk/products/halo-infinite")
        self.assertTrue(rows[0]["in_stock"])

    def test_card_fallback_does_not_turn_release_year_into_price(self):
        soup = soup_from(
            '<article><a href="/products/fc">EA Sports FC 2026</a><span>Coming soon</span></article>'
        )
        rows = _rows_from_cards(
            soup,
            store_name="Hit",
            base_url="https://hit.co.uk/search?q=fc",
            selectors="article",
            limit=4,
            allowed_hosts=("hit.co.uk",),
        )
        self.assertEqual(rows, [])

    @patch("apps.games.clients.uk_stores.fetch_html")
    def test_specialist_bs4_source_keeps_direct_product_links(self, fetch_html):
        fetch_html.return_value = (
            """
            <div class="card">
              <a href="/products/elden-ring-ps5"><h3>Elden Ring PS5</h3></a>
              <span class="price">£29.95 RRP £49.99</span>
            </div>
            """,
            200,
        )
        source = _try_specialist_uncached("tgc", "Elden Ring", "ps5", 4)
        self.assertFalse(source["blocked"])
        self.assertEqual(source["results"][0]["price"], Decimal("29.95"))
        self.assertEqual(
            source["results"][0]["url"],
            "https://www.thegamecollection.net/products/elden-ring-ps5",
        )

    def test_best_local_prefers_available_direct_offer(self):
        sources = {
            "one": {
                "results": [
                    {"name": "Halo Infinite", "store_name": "CeX", "price": Decimal("5"),
                     "url": "https://uk.webuy.com/search", "in_stock": False},
                    {"name": "Halo Infinite", "store_name": "CeX", "price": Decimal("8"),
                     "url": "https://uk.webuy.com/product/halo", "in_stock": True},
                ]
            },
            "two": {"results": [
                {"name": "Halo Infinite", "store_name": "Hit", "price": Decimal("10"),
                 "url": "https://hit.co.uk/products/halo", "in_stock": True}
            ]},
        }
        merged = merge_best_local(sources)
        self.assertEqual([row["price"] for row in merged], [Decimal("8"), Decimal("10")])
