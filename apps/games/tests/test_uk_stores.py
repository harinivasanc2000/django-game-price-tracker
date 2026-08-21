"""Accuracy rules shared by the polite BS4 UK retailer clients."""

from django.test import SimpleTestCase

from apps.games.clients.uk_stores import _keep_matching_rows, _title_matches


class UKStoreMatchingTests(SimpleTestCase):
    def test_rejects_unrelated_accessory_cards(self):
        self.assertTrue(_title_matches("Cyberpunk 2077 Ultimate Edition", "Cyberpunk 2077"))
        self.assertFalse(_title_matches("PlayStation 5 DualSense Controller", "Cyberpunk 2077"))

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
