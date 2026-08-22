"""Accuracy rules shared by the polite BS4 UK retailer clients."""

from django.test import SimpleTestCase

from apps.games.clients.uk_stores import _keep_matching_rows, _title_matches


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
