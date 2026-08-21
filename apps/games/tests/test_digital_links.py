"""Browser fallbacks for stores that deliberately block automated fetching."""

from django.test import SimpleTestCase

from apps.games.clients.digital_stores_bs4 import digital_search_links, try_cdkeys


class DigitalStoreLinkTests(SimpleTestCase):
    def test_loaded_replaces_the_redirecting_cdkeys_link(self):
        links = digital_search_links("Cyberpunk 2077")
        loaded = next(link for link in links if link["name"] == "Loaded (CDKeys)")
        self.assertIn("loaded.com/catalogsearch/result/", loaded["url"])
        self.assertIn("Cyberpunk+2077", loaded["url"])

    def test_loaded_scraper_soft_fails_to_its_search_link(self):
        result = try_cdkeys("Cyberpunk 2077")
        self.assertTrue(result["blocked"])
        self.assertIn("loaded.com", result["search_url"])
