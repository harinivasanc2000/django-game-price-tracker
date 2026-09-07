"""Private PS4 purchase checklist regressions."""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.games.models import Game, OwnedGame


class LibraryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="glasgow-player", password="safe")
        self.other = get_user_model().objects.create_user(username="other-player", password="safe")
        self.client.force_login(self.user)

    @patch("apps.games.library_view._safe_home_payload")
    def test_starter_adds_three_cex_ps4_purchases_and_filters_owned_deals(self, payload):
        payload.return_value = {
            "console_deals": [
                {"title": "God of War", "price_gbp": 5, "url": "https://example.test/gow", "store_name": "Shop"},
                {"title": "New PS4 Game", "price_gbp": 10, "url": "https://example.test/new", "store_name": "Shop"},
            ]
        }
        self.client.post(reverse("games:library_starter"))

        response = self.client.get(reverse("games:library"))

        self.assertEqual(OwnedGame.objects.filter(user=self.user).count(), 3)
        self.assertEqual(
            OwnedGame.objects.get(user=self.user, title="God of War (2018)").purchase_price,
            Decimal("8.00"),
        )
        self.assertContains(response, "New PS4 Game")
        self.assertNotContains(response, 'href="https://example.test/gow"')
        self.assertContains(response, "£20.00")

    @patch("apps.games.library_view._safe_home_payload", return_value={"console_deals": []})
    def test_manual_add_validates_and_saves_glasgow_purchase(self, _payload):
        response = self.client.post(
            reverse("games:library_add"),
            {"title": "Example", "purchase_price": "4.50", "retailer": "CeX", "location": "Glasgow"},
        )
        self.assertRedirects(response, reverse("games:library"))
        item = OwnedGame.objects.get(user=self.user)
        self.assertEqual(item.platform, Game.Platform.PS4)
        self.assertEqual(item.purchase_price, Decimal("4.50"))

    def test_toggle_and_delete_are_post_only_and_owner_scoped(self):
        item = OwnedGame.objects.create(user=self.user, title="Mine", purchase_price=5)
        foreign = OwnedGame.objects.create(user=self.other, title="Theirs", purchase_price=6)

        self.assertEqual(self.client.get(reverse("games:library_toggle", args=[item.pk])).status_code, 405)
        self.client.post(reverse("games:library_toggle", args=[item.pk]))
        item.refresh_from_db()
        self.assertTrue(item.completed)
        self.assertEqual(self.client.post(reverse("games:library_delete", args=[foreign.pk])).status_code, 404)
        self.client.post(reverse("games:library_delete", args=[item.pk]))
        self.assertFalse(OwnedGame.objects.filter(pk=item.pk).exists())

    def test_signup_makes_private_library_reachable(self):
        self.client.logout()
        response = self.client.post(
            reverse("games:signup"),
            {
                "username": "new-local-player",
                "password1": "safe-long-passphrase-4729",
                "password2": "safe-long-passphrase-4729",
            },
        )

        self.assertRedirects(
            response, reverse("games:library"), fetch_redirect_response=False
        )
        created = get_user_model().objects.get(username="new-local-player")
        self.assertEqual(int(self.client.session["_auth_user_id"]), created.pk)
