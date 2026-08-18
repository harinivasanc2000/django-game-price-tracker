"""
Fetch current CeX UK prices for God of War (PS4) and save as PriceRecords.

Usage:
    python manage.py fetch_cex_gow
"""

from django.core.management.base import BaseCommand
from apps.games.models import Game, Store, PriceRecord
from apps.games.clients.cex import find_god_of_war_ps4


class Command(BaseCommand):
    help = "Fetch CeX UK prices for God of War PS4 and store them"

    def handle(self, *args, **options):
        game, _ = Game.objects.get_or_create(
            slug="god-of-war-ps4",
            defaults={
                "title": "God of War",
                "platform": Game.Platform.PS4,
                "release_year": 2018,
                "is_active": True,
            },
        )
        store, _ = Store.objects.get_or_create(
            slug="cex-uk",
            defaults={
                "name": "CeX",
                "website": "https://uk.webuy.com",
                "store_type": Store.StoreType.PHYSICAL,
                "country": "GB",
                "notes": "Second-hand specialist",
            },
        )

        self.stdout.write("Searching CeX for God of War PS4...")
        results = find_god_of_war_ps4()

        if not results:
            self.stdout.write(self.style.WARNING("No matching products found."))
            return

        if results and "_error" in results[0]:
            self.stdout.write(self.style.ERROR(f"CeX request failed: {results[0]['_error']}"))
            self.stdout.write("The unofficial API may be blocked or changed. Try again later.")
            return

        created = 0
        for row in results:
            PriceRecord.objects.create(
                game=game,
                store=store,
                price=row["price"],
                currency=row.get("currency", "GBP"),
                url=row.get("url", ""),
                is_physical=True,
                is_used=True,
                condition=row.get("category") or "Used",
                in_stock=row.get("in_stock", True),
                notes=row.get("name", "")[:255],
            )
            created += 1
            self.stdout.write(f"  + {row['name']}: {row['price']} GBP")

        self.stdout.write(self.style.SUCCESS(f"\nSaved {created} price record(s) from CeX."))
