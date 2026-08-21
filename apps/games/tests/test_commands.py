"""Tests for developer-facing management command errors."""

from django.core.management import CommandError, call_command
from django.test import TestCase


class RefreshPricesCommandTests(TestCase):
    def test_missing_game_id_has_a_clear_error(self):
        with self.assertRaisesMessage(CommandError, "Tracked game id 999999 does not exist."):
            call_command("refresh_prices", game_id=999999)
