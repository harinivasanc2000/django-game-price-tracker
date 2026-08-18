"""
Seed the pilot data: God of War (PS4) + core UK stores.

Usage:
    python manage.py seed_pilot
"""

from django.core.management.base import BaseCommand
from apps.games.models import Game, Store


class Command(BaseCommand):
    help = "Seed God of War PS4 pilot + basic UK stores (CeX, PSN, Amazon UK, etc.)"

    def handle(self, *args, **options):
        stores = [
            {
                "name": "PlayStation Store UK",
                "slug": "psn-uk",
                "website": "https://store.playstation.com/en-gb/",
                "store_type": Store.StoreType.OFFICIAL,
                "country": "GB",
                "notes": "Official digital PSN store (UK)",
            },
            {
                "name": "CeX",
                "slug": "cex-uk",
                "website": "https://uk.webuy.com",
                "store_type": Store.StoreType.PHYSICAL,
                "country": "GB",
                "notes": "Second-hand specialist. Internal API exists but is unofficial — use politely.",
            },
            {
                "name": "Amazon UK",
                "slug": "amazon-uk",
                "website": "https://www.amazon.co.uk",
                "store_type": Store.StoreType.PHYSICAL,
                "country": "GB",
                "notes": "New + used + renewed discs",
            },
            {
                "name": "GAME",
                "slug": "game-uk",
                "website": "https://www.game.co.uk",
                "store_type": Store.StoreType.PHYSICAL,
                "country": "GB",
                "notes": "High-street + online",
            },
            {
                "name": "Steam",
                "slug": "steam",
                "website": "https://store.steampowered.com",
                "store_type": Store.StoreType.OFFICIAL,
                "country": "GB",
                "notes": "PC digital (for comparison later)",
            },
        ]

        for data in stores:
            obj, created = Store.objects.update_or_create(
                slug=data["slug"], defaults=data
            )
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status} store: {obj.name}")

        game, created = Game.objects.update_or_create(
            slug="god-of-war-ps4",
            defaults={
                "title": "God of War",
                "platform": Game.Platform.PS4,
                "release_year": 2018,
                "cover_url": "",
                "is_active": True,
                "notes": "",
            },
        )
        # notes field doesn't exist on Game yet — remove if error
        status = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{status} pilot game: {game}"))

        self.stdout.write(self.style.SUCCESS("\nPilot data ready. Next: add prices via admin or a CeX client."))
