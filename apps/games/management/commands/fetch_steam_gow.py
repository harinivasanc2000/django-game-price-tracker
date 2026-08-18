"""
Fetch current Steam (UK) price for God of War and save as PriceRecord.

Usage:
    python manage.py fetch_steam_gow
    python manage.py fetch_steam_gow --country US
"""

from django.core.management.base import BaseCommand
from apps.games.models import Game, Store, PriceRecord
from apps.games.clients.steam import get_god_of_war_steam, GOD_OF_WAR_STEAM_APP_ID


class Command(BaseCommand):
    help = "Fetch Steam price for God of War (PC) and store it"

    def add_arguments(self, parser):
        parser.add_argument(
            "--country",
            default="GB",
            help="Steam country code (default: GB for UK prices)",
        )

    def handle(self, *args, **options):
        country = options["country"].upper()

        game, _ = Game.objects.update_or_create(
            slug="god-of-war-pc",
            defaults={
                "title": "God of War",
                "platform": Game.Platform.PC,
                "steam_app_id": GOD_OF_WAR_STEAM_APP_ID,
                "release_year": 2022,  # PC release
                "is_active": True,
            },
        )

        store, _ = Store.objects.get_or_create(
            slug="steam",
            defaults={
                "name": "Steam",
                "website": "https://store.steampowered.com",
                "store_type": Store.StoreType.OFFICIAL,
                "country": country if len(country) == 2 else "GB",
                "notes": "Official PC digital store",
            },
        )

        self.stdout.write(f"Fetching Steam price for God of War (cc={country})...")
        result = get_god_of_war_steam(country=country)

        if not result:
            self.stdout.write(self.style.ERROR("Could not fetch Steam price. Try again later."))
            return

        rec = PriceRecord.objects.create(
            game=game,
            store=store,
            price=result["price"],
            currency=result["currency"],
            original_price=result.get("original"),
            discount_percent=result.get("discount") or None,
            url=result["url"],
            is_physical=False,
            is_used=False,
            in_stock=True,
            notes=result.get("name", "")[:255],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Saved: {result['name']} — {result['price']} {result['currency']}"
                + (f" (-{result['discount']}%)" if result.get("discount") else "")
            )
        )
        self.stdout.write(f"  View: http://127.0.0.1:8000/game/{game.slug}/")
        self.stdout.write(f"  Steam: {result['url']}")
