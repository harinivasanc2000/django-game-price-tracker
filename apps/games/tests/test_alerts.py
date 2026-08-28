"""Price alerts should lead users to both the deal and tracker page."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from apps.games.models import Game, PriceAlert, Watch
from apps.games.tasks import send_pending_alerts


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SITE_URL="https://tracker.example",
)
class PriceAlertEmailTests(TestCase):
    def test_email_contains_direct_offer_and_tracker_links(self):
        user = get_user_model().objects.create_user(
            username="watcher", email="watcher@example.test", password="safe-password"
        )
        game = Game.objects.create(title="Alert game", slug="alert-game")
        watch = Watch.objects.create(
            user=user, game=game, target_price=Decimal("15.00")
        )
        alert = PriceAlert.objects.create(
            watch=watch,
            price=Decimal("9.99"),
            target_price=Decimal("15.00"),
            store="Example Store",
            url="https://retailer.example/products/alert-game",
        )

        result = send_pending_alerts()

        self.assertEqual(result["sent"], 1)
        self.assertIn(alert.url, mail.outbox[0].body)
        self.assertIn("https://tracker.example/game/alert-game/", mail.outbox[0].body)
        alert.refresh_from_db()
        self.assertTrue(alert.is_sent)
