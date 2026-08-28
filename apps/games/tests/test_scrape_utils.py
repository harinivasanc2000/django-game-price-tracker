"""Regression tests for the defensive BeautifulSoup extraction helpers."""

from decimal import Decimal

from django.test import SimpleTestCase

from apps.games.clients.scrape_utils import (
    extract_ld_json_products,
    normalise_public_url,
    parse_money,
    parse_rating,
    product_row,
    soup_from,
)


class ScrapeUtilityTests(SimpleTestCase):
    def test_money_parser_prefers_live_gbp_price(self):
        self.assertEqual(parse_money("£9.95 RRP £25.99"), Decimal("9.95"))
        self.assertEqual(parse_money("Was £59.99 now £39.99"), Decimal("39.99"))
        self.assertEqual(
            parse_money("Released 2024 · Cyberpunk 2077 · £24.50", require_currency=True),
            Decimal("24.50"),
        )

    def test_money_parser_does_not_treat_year_or_foreign_price_as_gbp(self):
        self.assertIsNone(parse_money("EA Sports FC 2026", require_currency=True))
        self.assertIsNone(parse_money("€29.99"))
        self.assertIsNone(parse_money("$39.99"))

    def test_rating_parser_requires_rating_context(self):
        self.assertEqual(parse_rating("4.75 out of 5 stars"), 4.75)
        self.assertIsNone(parse_rating("PEGI 18 released in 2025"))

    def test_public_url_normalisation_blocks_unsafe_and_cross_site_urls(self):
        base = "https://www.example.co.uk/search?q=halo"
        self.assertEqual(
            normalise_public_url(
                "/products/halo#reviews", base_url=base, allowed_hosts=("example.co.uk",)
            ),
            "https://www.example.co.uk/products/halo",
        )
        self.assertEqual(
            normalise_public_url(
                "https://attacker.test/offer", base_url=base, allowed_hosts=("example.co.uk",)
            ),
            "",
        )
        self.assertEqual(normalise_public_url("javascript:alert(1)"), "")

    def test_product_row_rejects_non_finite_prices(self):
        self.assertIsNone(product_row(name="Halo", price=Decimal("NaN")))
        self.assertIsNone(product_row(name="Halo", price=Decimal("Infinity")))

    def test_json_ld_walker_prefers_gbp_and_deduplicates_graph_nodes(self):
        html = """
        <script type="application/ld+json">
        {"@graph": [
          {"@type": "Product", "name": "Halo Infinite (Xbox)",
           "url": "/products/halo", "offers": [
             {"@type": "Offer", "price": "59.99", "priceCurrency": "USD"},
             {"@type": "Offer", "price": "24.99", "priceCurrency": "GBP",
              "availability": "https://schema.org/InStock"}
           ]},
          {"@type": "Product", "name": "Halo Infinite (Xbox)",
           "url": "/products/halo", "offers":
             {"price": "24.99", "priceCurrency": "GBP"}}
        ]}
        </script>
        """
        products = extract_ld_json_products(soup_from(html))
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["price"], "24.99")
        self.assertTrue(products[0]["in_stock"])

