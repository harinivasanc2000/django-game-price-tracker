"""Refreshes keep a compact history without mixing platform-specific offers."""

from copy import deepcopy
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.games.models import Game, PriceRecord
from apps.games.tasks import refresh_one_game


class CrossPlatformRefreshTests(TestCase):
    def setUp(self):
        self.game = Game.objects.create(
            title="Everywhere Game",
            slug="everywhere-game",
            platform=Game.Platform.PS5,
        )
        self.bundle = {
            "psn_rows": [
                {"name": "Everywhere Game PS5", "price": "39.99", "currency": "GBP",
                 "url": "https://store.playstation.com/en-gb/product/example"},
            ],
            "xbox_rows": [
                {"name": "Everywhere Game Xbox", "price": "34.99", "currency": "GBP",
                 "has_price": True, "url": "https://www.xbox.com/en-GB/games/store/example"},
            ],
            "nintendo_rows": [
                {"name": "Everywhere Game Switch", "price": "44.99", "currency": "GBP",
                 "has_price": True, "url": "https://www.nintendo.com/en-gb/Games/example"},
            ],
            "game_rows": [
                {"name": "Sold out", "price": "1.00", "in_stock": False,
                 "url": "https://www.game.co.uk/sold-out"},
                {"name": "Everywhere Game", "price": "29.99", "in_stock": True,
                 "url": "https://www.game.co.uk/everywhere-game"},
            ],
            "specialist_sources": [
                {
                    "key": "shopto",
                    "label": "ShopTo",
                    "rows": [
                        {"name": "Everywhere Game", "price": "27.99", "currency": "GBP",
                         "in_stock": True, "url": "https://www.shopto.net/en/example"}
                    ],
                    "search_url": "https://www.shopto.net/en/search/?input_search=Everywhere+Game",
                }
            ],
        }
        self.deals = [
            {"store_name": "Fanatical", "price": "24.99", "currency": "GBP",
             "url": "https://www.cheapshark.com/redirect?dealID=one"},
            {"store_name": "Fanatical", "price": "25.99", "currency": "GBP",
             "url": "https://www.cheapshark.com/redirect?dealID=two"},
        ]

    @patch("apps.games.tasks.to_gbp_or_zero", side_effect=lambda value, _currency: Decimal(str(value)))
    @patch("apps.games.tasks.get_app_details")
    @patch("apps.games.tasks.deals_for_title")
    @patch("apps.games.tasks.platform_bundle")
    def test_ps5_game_records_psn_and_uk_sources_without_other_platforms(
        self, bundle, deals, get_detail, _to_gbp
    ):
        bundle.return_value = deepcopy(self.bundle)
        deals.return_value = deepcopy(self.deals)

        first = refresh_one_game(self.game)

        get_detail.assert_not_called()
        deals.assert_not_called()
        bundle.assert_called_once_with(self.game.title, Game.Platform.PS5)
        self.assertTrue(first["psn"])
        self.assertFalse(first["xbox"])
        self.assertFalse(first["nintendo"])
        self.assertTrue(first["uk"])
        self.assertFalse(first["third_party"])
        self.assertEqual(first["sources_observed"], 3)
        self.assertEqual(first["snapshots_created"], 3)
        self.assertEqual(PriceRecord.objects.count(), 3)
        self.assertFalse(PriceRecord.objects.filter(price=Decimal("1.00")).exists())
        self.assertEqual(
            set(PriceRecord.objects.values_list("store__slug", flat=True)),
            {"psn-uk", "game-uk", "shopto-uk"},
        )

        second = refresh_one_game(self.game)
        self.assertEqual(second["snapshots_created"], 0)
        self.assertEqual(PriceRecord.objects.count(), 3)

        # An irrelevant Xbox price change must not leak into PS5 history.
        changed = deepcopy(self.bundle)
        changed["xbox_rows"][0]["price"] = "19.99"
        bundle.return_value = changed
        third = refresh_one_game(self.game)

        self.assertEqual(third["snapshots_created"], 0)
        self.assertEqual(PriceRecord.objects.count(), 3)
        self.assertFalse(PriceRecord.objects.filter(store__slug="xbox-uk").exists())

        # A real PSN change remains append-only history for the selected platform.
        changed["psn_rows"][0]["price"] = "19.99"
        fourth = refresh_one_game(self.game)

        self.assertEqual(fourth["snapshots_created"], 1)
        self.assertEqual(PriceRecord.objects.count(), 4)
        self.assertEqual(
            list(
                PriceRecord.objects.filter(store__slug="psn-uk")
                .order_by("recorded_at", "pk")
                .values_list("price", flat=True)
            ),
            [Decimal("39.99"), Decimal("19.99")],
        )

        sold_out = deepcopy(changed)
        sold_out["game_rows"] = [
            {"name": "Everywhere Game", "price": "29.99", "in_stock": False,
             "url": "https://www.game.co.uk/everywhere-game"}
        ]
        bundle.return_value = sold_out
        fifth = refresh_one_game(self.game)

        self.assertEqual(fifth["snapshots_created"], 1)
        latest_game = PriceRecord.objects.filter(store__slug="game-uk").latest("recorded_at", "pk")
        self.assertFalse(latest_game.in_stock)
