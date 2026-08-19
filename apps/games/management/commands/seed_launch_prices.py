"""
Seed approximate public launch / MSRP prices.

Usage:
    python manage.py seed_launch_prices
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from apps.games.models import Game, AdminChangeLog

LAUNCH_DATA = [
    (1593500, "God of War", "pc", 2022, "49.99", "Steam PC launch ~£49.99 (2022) public listing"),
    (1091500, "Cyberpunk 2077", "pc", 2020, "49.99", "Steam/PC standard edition launch ~£49.99"),
    (271590, "Grand Theft Auto V", "pc", 2015, "39.99", "PC launch period common RRP ~£39.99"),
    (1174180, "Red Dead Redemption 2", "pc", 2019, "59.99", "PC launch ~£59.99 public"),
    (292030, "The Witcher 3: Wild Hunt", "pc", 2015, "29.99", "PC launch era ~£29.99 standard"),
    (1245620, "ELDEN RING", "pc", 2022, "49.99", "Steam PC launch ~£49.99"),
    (814380, "Sekiro: Shadows Die Twice", "pc", 2019, "49.99", "PC launch ~£49.99"),
    (1086940, "Baldur's Gate 3", "pc", 2023, "59.99", "Steam full release ~£59.99"),
    (1888930, "The Last of Us Part I", "pc", 2023, "49.99", "PC launch ~£49.99"),
    (1817070, "Marvel's Spider-Man Remastered", "pc", 2022, "49.99", "PC launch ~£49.99"),
    (2050650, "Resident Evil 4", "pc", 2023, "49.99", "RE4 Remake PC ~£49.99 launch"),
    (108710, "Yakuza Kiwami", "pc", 2019, "15.99", "Steam PC ~£15.99 common UK listing era"),
    (834530, "Yakuza Kiwami 2", "pc", 2019, "24.99", "Steam PC approximate launch RRP"),
    (1113000, "Persona 5 Royal", "pc", 2022, "49.99", "PC launch ~£49.99"),
    (1145360, "Hades", "pc", 2020, "19.99", "1.0 launch ~£19.99"),
]


def _unique_slug(base: str, app_id: int) -> str:
    """Slug that never collides: prefer title-pc, else title-pc-appid."""
    base = (base or f"steam-{app_id}")[:160]
    if not Game.objects.filter(slug=base).exclude(steam_app_id=app_id).exists():
        return base
    return f"{base}-{app_id}"[:180]


class Command(BaseCommand):
    help = "Seed public reference launch prices on Game rows"

    def handle(self, *args, **options):
        updated = 0
        for app_id, title, platform, year, price, source in LAUNCH_DATA:
            launch = Decimal(price)
            game = Game.objects.filter(steam_app_id=app_id).first()
            if game:
                # Only update launch fields; never force is_active=False if already tracked
                game.launch_price = launch
                game.launch_currency = "GBP"
                game.launch_price_source = source
                if not game.release_year:
                    game.release_year = year
                game.save()
            else:
                slug = _unique_slug(slugify(f"{title}-pc"), app_id)
                # If slug taken by another row without this steam id, attach launch to that row if same title
                conflict = Game.objects.filter(slug=slug).first()
                if conflict and not conflict.steam_app_id:
                    conflict.steam_app_id = app_id
                    conflict.launch_price = launch
                    conflict.launch_currency = "GBP"
                    conflict.launch_price_source = source
                    conflict.release_year = year
                    conflict.save()
                    game = conflict
                else:
                    slug = _unique_slug(slugify(f"{title}-pc"), app_id)
                    game = Game.objects.create(
                        steam_app_id=app_id,
                        title=title,
                        slug=slug,
                        platform=Game.Platform.PC,
                        release_year=year,
                        launch_price=launch,
                        launch_currency="GBP",
                        launch_price_source=source,
                        is_active=False,
                    )
            updated += 1
            self.stdout.write(f"  {title}: £{price}")

        AdminChangeLog.objects.create(
            actor="seed_launch_prices",
            action="seed_launch_prices",
            details=f"Seeded/updated {updated} public launch price references",
        )
        self.stdout.write(self.style.SUCCESS(f"Done: {updated} titles."))
