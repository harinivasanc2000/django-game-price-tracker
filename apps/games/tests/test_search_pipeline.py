"""Regression tests for cross-platform search ranking, filters, and caching."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.games.platform_search import (
    _cache_key,
    _filter_psn_generation,
    _outbound_search_links,
    _price_filter_rows,
    multi_platform_search,
    normalise_search_query,
)
from apps.games.search_sort import normalise_sort, sort_results


class SearchSortTests(SimpleTestCase):
    def test_descending_price_keeps_unknown_and_nan_prices_last(self):
        rows = [
            {"name": "Unknown", "price": None, "price_status": "unknown"},
            {"name": "Cheap", "price": 5, "price_status": "paid"},
            {"name": "Broken", "price": "NaN", "price_status": "paid"},
            {"name": "Expensive", "price": 60, "price_status": "paid"},
        ]

        ordered = sort_results(rows, "price_desc")

        self.assertEqual([row["name"] for row in ordered], ["Expensive", "Cheap", "Broken", "Unknown"])

    def test_value_ranking_prefers_title_match_then_real_saving(self):
        rows = [
            {
                "name": "Loose cheap match",
                "match_score": 0.67,
                "price": 1,
                "original": 100,
                "discount": 99,
                "price_status": "paid",
            },
            {
                "name": "Exact full-price match",
                "match_score": 1,
                "price": 30,
                "original": 30,
                "discount": 0,
                "price_status": "paid",
            },
            {
                "name": "Exact discounted match",
                "match_score": 1,
                "price": 20,
                "original": 60,
                "discount": 67,
                "price_status": "paid",
            },
        ]

        ordered = sort_results(rows, "value")

        self.assertEqual(ordered[0]["name"], "Exact discounted match")
        self.assertEqual(ordered[-1]["name"], "Loose cheap match")

    def test_unknown_sort_name_falls_back_to_relevance(self):
        self.assertEqual(normalise_sort("DROP TABLE"), "relevance")


class SearchFilterTests(SimpleTestCase):
    def test_price_band_excludes_unknown_rows_and_supports_availability(self):
        rows = [
            {"name": "Paid", "price": 8, "price_status": "paid", "discount": 20},
            {"name": "Too dear", "price": 30, "price_status": "paid", "discount": 50},
            {"name": "Free", "price": 0, "price_status": "free", "discount": 0},
            {"name": "Unknown", "price": None, "price_status": "unknown"},
        ]

        under_ten = _price_filter_rows(rows, max_price=10)
        paid = _price_filter_rows(rows, availability="priced")
        free = _price_filter_rows(rows, availability="free")

        self.assertEqual([row["name"] for row in under_ten], ["Paid", "Free"])
        self.assertEqual([row["name"] for row in paid], ["Paid", "Too dear"])
        self.assertEqual([row["name"] for row in free], ["Free"])

    def test_minimum_discount_requires_trustworthy_discount_metadata(self):
        rows = [
            {"name": "Steam full price", "price": 20, "discount": 0},
            {"name": "Steam sale", "price": 15, "discount": 25},
            {"name": "Console without discount metadata", "price": 18},
        ]

        filtered = _price_filter_rows(rows, min_discount=25)

        self.assertEqual(
            [row["name"] for row in filtered],
            ["Steam sale"],
        )

    def test_psn_generation_filter_uses_metadata_but_keeps_unknowns(self):
        rows = [
            {"name": "PS4 version", "platforms": ["PS4"]},
            {"name": "PS5 version", "platforms": ["PlayStation 5"]},
            {"name": "Unknown version", "platforms": []},
        ]

        filtered = _filter_psn_generation(rows, "ps5")

        self.assertEqual([row["name"] for row in filtered], ["PS5 version", "Unknown version"])


class SearchPerformanceTests(TestCase):
    def tearDown(self):
        cache.clear()

    @patch("apps.games.platform_search.search_store")
    def test_filter_changes_reuse_one_raw_platform_search(self, search_store):
        cache.clear()
        search_store.return_value = [
            {
                "app_id": 70,
                "name": "Hades",
                "price": 8,
                "currency": "GBP",
                "price_status": "paid",
                "discount": 20,
                "url": "https://store.steampowered.com/app/70/",
            }
        ]

        first = multi_platform_search("Hades", platform="pc", max_price=10)
        second = multi_platform_search("Hades", platform="pc", max_price=5)

        self.assertEqual(len(first["steam"]), 1)
        self.assertEqual(second["steam"], [])
        search_store.assert_called_once_with("Hades", country="GB", limit=12)

    def test_query_normalisation_and_cache_key_are_backend_safe(self):
        query = normalise_search_query("  Pokémon\x00   Scarlet\nViolet ")
        key = _cache_key(query, "switch", "GB", 14)

        self.assertEqual(query, "Pokémon Scarlet Violet")
        self.assertLess(len(key), 50)
        self.assertNotIn("Pokémon", key)
        self.assertNotIn(" ", key)

    def test_outbound_links_are_encoded_grouped_and_forward_uk_filters(self):
        links = _outbound_search_links(
            "Baldur's Gate 3 & extras",
            "ps5",
            "",
            min_price=10,
            max_price=40,
            condition="used",
        )
        by_name = {link["name"]: link for link in links}

        self.assertIn("PlayStation Store UK", by_name)
        self.assertNotIn("Steam", by_name)
        self.assertIn("CeX", by_name)
        self.assertIn("eBay UK", by_name)
        self.assertIn("%26", by_name["PlayStation Store UK"]["url"])
        self.assertIn("_udlo=10", by_name["eBay UK"]["url"])
        self.assertIn("_udhi=40", by_name["eBay UK"]["url"])
        self.assertIn("LH_ItemCondition=3000", by_name["eBay UK"]["url"])
        self.assertTrue(all(link.get("group") for link in links))


class SearchViewTests(TestCase):
    @patch("apps.games.search_view.cheapest_hint", return_value=None)
    @patch("apps.games.search_view.multi_platform_search")
    def test_view_sanitises_filters_and_sorts_every_platform(self, search, _cheapest):
        search.return_value = {
            "steam": [],
            "psn": [
                {"name": "Unknown", "price": None, "price_status": "unknown"},
                {"name": "Paid", "price": 20, "currency": "GBP"},
            ],
            "xbox": [],
            "nintendo": [],
            "links": [],
            "nintendo_blocked": True,
            "nintendo_search_url": "",
        }

        response = self.client.get(
            reverse("games:steam_search"),
            {
                "q": "  Hades\x00   II ",
                "platform": "unsupported",
                "sort": "price_desc",
                "min_price": "50",
                "max_price": "10",
                "availability": "invalid",
                "min_discount": "250",
                "condition": "damaged",
                "limit": "15",
            },
        )

        self.assertEqual(response.status_code, 200)
        kwargs = search.call_args.kwargs
        self.assertEqual(search.call_args.args[0], "Hades II")
        self.assertEqual(kwargs["platform"], "")
        self.assertEqual(kwargs["country"], "GB")
        self.assertEqual((kwargs["min_price"], kwargs["max_price"]), (10.0, 50.0))
        self.assertEqual(kwargs["availability"], "any")
        self.assertEqual(kwargs["min_discount"], 100)
        self.assertEqual(kwargs["condition"], "")
        self.assertEqual(kwargs["limit"], 16)
        self.assertEqual([row["name"] for row in response.context["psn_results"]], ["Paid", "Unknown"])
        self.assertContains(response, "were swapped into the correct order")

    @patch("apps.games.search_view.cheapest_hint", return_value=None)
    @patch("apps.games.search_view.multi_platform_search")
    def test_search_page_renders_advanced_filter_controls(self, search, _cheapest):
        search.return_value = {
            "steam": [],
            "psn": [],
            "xbox": [],
            "nintendo": [],
            "links": [
                {
                    "name": "CeX",
                    "url": "https://uk.webuy.com/search?stext=Hades",
                    "group": "UK shops & marketplaces",
                    "kind": "used-physical",
                    "note": "Used games",
                }
            ],
            "nintendo_blocked": True,
            "nintendo_search_url": "",
        }

        response = self.client.get(reverse("games:steam_search"), {"q": "Hades"})

        self.assertContains(response, 'name="availability"')
        self.assertContains(response, 'name="min_discount"')
        self.assertContains(response, 'name="condition"')
        self.assertContains(response, 'value="value"')
        self.assertContains(response, "Search 1 UK store and comparison sites directly")
        self.assertContains(response, "document.createTextNode")
        self.assertNotContains(response, "dd.innerHTML")
