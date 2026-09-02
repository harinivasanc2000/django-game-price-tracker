"""Offline regressions for platform-aware home deals and motion enhancements."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.games.clients.platform_deals import (
    parse_playstation_deals,
    parse_switch_deals,
    parse_xbox_deals,
)
from apps.games.home_view import _build_console_home_payload, normalise_home_platform
from apps.games.models import Game, PriceRecord, Store


class PlatformDealParserTests(SimpleTestCase):
    """Small representative documents keep retailer parser tests offline."""

    def test_playstation_parser_filters_generation_and_extracts_offer_fields(self):
        html = """
        <main>
          <a href="/gb/game/example-ps4">
            <img src="https://psndeal.com/example-ps4.jpg">
            <span>-50%</span><span>PS4</span>
            <h3>Example PS4 Adventure</h3>
            <span>£9.99</span><span class="line-through">£19.99</span>
          </a>
          <a href="/gb/game/example-ps5">
            <span>-25%</span><span>PS5</span>
            <h3>Example PS5 Adventure</h3>
            <span>£29.99</span><span class="line-through">£39.99</span>
          </a>
        </main>
        """

        rows = parse_playstation_deals(html, "ps4")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Example PS4 Adventure")
        self.assertEqual(rows[0]["platform"], "ps4")
        self.assertEqual(rows[0]["price_gbp"], 9.99)
        self.assertEqual(rows[0]["original_gbp"], 19.99)
        self.assertEqual(rows[0]["discount"], 50)
        self.assertEqual(rows[0]["image"], "https://psndeal.com/example-ps4.jpg")
        self.assertEqual(rows[0]["url"], "https://psndeal.com/gb/game/example-ps4")
        self.assertEqual(rows[0]["store_name"], "PSNDeal")
        self.assertEqual(rows[0]["source_kind"], "aggregator")

    def test_xbox_parser_extracts_current_and_original_price(self):
        html = """
        <section class="gameDiv">
          <a href="https://www.xbox.com/en-GB/games/store/example/id">
            <img src="https://store-images.s-microsoft.com/example.jpg">
            <span>50% OFF</span>
            <h3 class="x1GameName">Example Xbox Racer</h3>
            <div class="c-price">
              <s>£19.99</s><span class="textpricenew">£9.99</span>
            </div>
          </a>
        </section>
        """

        rows = parse_xbox_deals(html)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Example Xbox Racer")
        self.assertEqual(rows[0]["platform"], "xbox")
        self.assertEqual(rows[0]["price_gbp"], 9.99)
        self.assertEqual(rows[0]["original_gbp"], 19.99)
        self.assertEqual(rows[0]["discount"], 50)
        self.assertEqual(rows[0]["url"], "https://www.xbox.com/en-GB/games/store/example/id")
        self.assertEqual(rows[0]["store_name"], "Xbox / Microsoft Store")
        self.assertEqual(rows[0]["source_kind"], "official")

    def test_switch_parser_extracts_relative_link_and_discount(self):
        html = """
        <a class="game-container" href="/game/1-example">
          <img src="https://imgcdn.platprices.com/example.webp" alt="Example">
          <div class="game-tile-platform">Switch</div>
          <div class="game-tile-discount">-50%</div>
          <div class="game-name">Example Island</div>
          <div class="game-price">
            £9.99 <span class="strike-price">£19.99</span>
          </div>
        </a>
        """

        rows = parse_switch_deals(html)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Example Island")
        self.assertEqual(rows[0]["platform"], "switch")
        self.assertEqual(rows[0]["price_gbp"], 9.99)
        self.assertEqual(rows[0]["original_gbp"], 19.99)
        self.assertEqual(rows[0]["discount"], 50)
        self.assertEqual(rows[0]["url"], "https://ntprices.com/game/1-example")
        self.assertEqual(rows[0]["store_name"], "NTPrices")
        self.assertEqual(rows[0]["source_kind"], "aggregator")


class HomePlatformHelperTests(SimpleTestCase):
    def test_platform_normalisation_is_bounded_and_case_insensitive(self):
        self.assertEqual(normalise_home_platform("  PS4  "), "ps4")
        self.assertEqual(normalise_home_platform("PC"), "pc")
        self.assertEqual(normalise_home_platform("switch"), "switch")
        self.assertEqual(normalise_home_platform("unsupported"), "")
        self.assertEqual(normalise_home_platform(None), "")


class ConsoleHomePayloadTests(TestCase):
    def tearDown(self):
        cache.clear()

    @patch("apps.games.home_view.console_deals", return_value=[])
    def test_ps4_feed_uses_only_fresh_ps4_snapshots(self, _console_deals):
        store = Store.objects.create(name="UK Game Shop", slug="uk-game-shop")
        fresh_ps4 = Game.objects.create(
            title="Fresh PS4 Deal",
            slug="fresh-ps4-deal",
            platform=Game.Platform.PS4,
            cover_url="https://example.test/fresh.jpg",
        )
        stale_ps4 = Game.objects.create(
            title="Stale PS4 Deal",
            slug="stale-ps4-deal",
            platform=Game.Platform.PS4,
        )
        ps5 = Game.objects.create(
            title="Different PS5 Deal",
            slug="different-ps5-deal",
            platform=Game.Platform.PS5,
        )
        PriceRecord.objects.create(
            game=fresh_ps4,
            store=store,
            price=Decimal("14.99"),
            original_price=Decimal("29.99"),
            discount_percent=50,
            url="https://example.test/fresh-ps4",
        )
        stale = PriceRecord.objects.create(
            game=stale_ps4,
            store=store,
            price=Decimal("4.99"),
            original_price=Decimal("39.99"),
            discount_percent=88,
        )
        PriceRecord.objects.create(
            game=ps5,
            store=store,
            price=Decimal("9.99"),
            original_price=Decimal("59.99"),
            discount_percent=83,
        )
        old = timezone.now() - timedelta(days=8)
        PriceRecord.objects.filter(pk=stale.pk).update(
            recorded_at=old,
            last_checked_at=old,
        )

        payload = _build_console_home_payload("ps4")
        titles = [row["title"] for row in payload["console_deals"]]

        self.assertTrue(payload["console_feed"])
        self.assertEqual(payload["platform_label"], "PS4")
        self.assertIn("Fresh PS4 Deal", titles)
        self.assertNotIn("Stale PS4 Deal", titles)
        self.assertNotIn("Different PS5 Deal", titles)
        self.assertTrue(all(row["platform"] == "ps4" for row in payload["console_deals"]))


class HomePlatformViewTests(TestCase):
    def setUp(self):
        # Home payloads deliberately outlive a request; isolate each assertion
        # from cache values created by another test.
        cache.clear()

    def tearDown(self):
        cache.clear()

    @staticmethod
    def _ps4_payload(title="Escaped <PS4> Deal"):
        return {
            "console_deals": [
                {
                    "title": title,
                    "platform": "ps4",
                    "price_gbp": 9.99,
                    "original_gbp": 19.99,
                    "discount": 50,
                    "image": "",
                    "url": "https://example.test/ps4-deal",
                    "store_name": "PSNDeal",
                    "source_kind": "aggregator",
                }
            ],
            "console_feed": True,
            "platform_label": "PS4",
            "browse_url": "https://store.playstation.com/en-gb/pages/deals",
            "feed_heading": "PS4 deals and discounts",
            "feed_intro": "Current UK PS4 offers.",
            "_cache_incomplete": False,
        }

    @patch("apps.games.home_view._build_console_home_payload")
    def test_fragment_get_renders_selected_platform_as_escaped_html(self, build):
        cache.clear()
        build.return_value = self._ps4_payload()

        response = self.client.get(
            reverse("games:home_deals_fragment"),
            {"platform": "ps4"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PS4 deals and discounts")
        self.assertContains(response, "Escaped &lt;PS4&gt; Deal")
        self.assertNotContains(response, "Escaped <PS4> Deal", html=False)
        self.assertContains(response, 'href="https://example.test/ps4-deal"')
        build.assert_called_once_with("ps4")

    @patch("apps.games.home_view._build_home_payload")
    def test_invalid_fragment_platform_falls_back_without_echoing_input(self, build):
        cache.clear()
        build.return_value = {
            "popular_cards": [],
            "hot_deals": [],
            "public_specials": [],
            "seasonal_window_days": 90,
        }

        response = self.client.get(
            reverse("games:home_deals_fragment"),
            {"platform": "<script>bad</script>"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script>bad</script>")

    @patch("apps.games.home_view._build_console_home_payload")
    def test_home_query_progressively_renders_and_selects_ps4(self, build):
        cache.clear()
        build.return_value = self._ps4_payload("Progressive PS4 Deal")

        response = self.client.get(reverse("games:home"), {"platform": "ps4"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_platform"], "ps4")
        self.assertContains(response, "Progressive PS4 Deal")
        self.assertContains(response, '<option value="ps4" selected>PS4</option>', html=True)


class HomeEnhancementSourceTests(SimpleTestCase):
    def test_home_feed_is_race_safe_accessible_and_motion_optional(self):
        html = render_to_string(
            "games/home.html",
            {
                "popular_cards": [],
                "hot_deals": [],
                "public_specials": [],
                "console_deals": [],
                "current_platform": "",
                "seasonal_window_days": 90,
            },
        )

        self.assertIn("AbortController", html)
        self.assertIn("aria-busy", html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn("IntersectionObserver", html)
        self.assertIn("@media (prefers-reduced-motion: reduce)", html)
