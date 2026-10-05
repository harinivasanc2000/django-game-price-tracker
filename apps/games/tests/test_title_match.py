"""Strict title matching — Arkham Knight must not match LEGO / Asylum."""

from django.test import SimpleTestCase

from apps.games.clients.title_match import (
    filter_by_title,
    title_match_score,
    titles_match,
)


class TitleMatchTests(SimpleTestCase):
    QUERY = "Batman: Arkham Knight"

    def test_accepts_real_arkham_knight_listings(self):
        self.assertTrue(titles_match("Batman Arkham Knight PS4", self.QUERY))
        self.assertTrue(
            titles_match("Batman: Arkham Knight Game of the Year Edition", self.QUERY)
        )
        self.assertGreaterEqual(
            title_match_score("Batman Arkham Knight GOTY", self.QUERY), 0.67
        )

    def test_rejects_lego_batman(self):
        self.assertFalse(titles_match("LEGO Batman 3: Beyond Gotham", self.QUERY))
        self.assertFalse(titles_match("Lego Batman 2 DC Super Heroes", self.QUERY))
        self.assertEqual(title_match_score("LEGO Batman", self.QUERY), 0.0)

    def test_rejects_other_arkham_entries(self):
        self.assertFalse(titles_match("Batman: Arkham Asylum", self.QUERY))
        self.assertFalse(titles_match("Batman Arkham City GOTY", self.QUERY))
        self.assertFalse(titles_match("Batman Arkham Origins", self.QUERY))

    def test_rejects_generic_batman_only(self):
        self.assertFalse(titles_match("Batman The Telltale Series", self.QUERY))

    def test_filter_by_title_keeps_only_knight(self):
        rows = [
            {"name": "LEGO Batman 3", "price": 5},
            {"name": "Batman Arkham Asylum", "price": 8},
            {"name": "Batman Arkham Knight PS4", "price": 12},
            {"name": "Batman Arkham Knight", "price": 9},
        ]
        kept = filter_by_title(rows, self.QUERY)
        names = [r["name"] for r in kept]
        self.assertEqual(len(names), 2)
        self.assertTrue(all("knight" in n.lower() for n in names))
        self.assertTrue(all("lego" not in n.lower() for n in names))

    def test_god_of_war_not_confused_with_ragnarok(self):
        self.assertFalse(titles_match("God of War Ragnarök", "God of War"))
        score = title_match_score("God of War Ragnarök", "God of War")
        self.assertLess(score, 0.67)

    def test_spider_man_not_miles(self):
        self.assertFalse(
            titles_match("Marvel's Spider-Man: Miles Morales", "Marvel's Spider-Man")
        )

    def test_horizon_not_forbidden_west(self):
        self.assertFalse(titles_match("Horizon Forbidden West", "Horizon Zero Dawn"))

    def test_cyberpunk_accepts_editions(self):
        self.assertTrue(
            titles_match("Cyberpunk 2077 Ultimate Edition", "Cyberpunk 2077")
        )
