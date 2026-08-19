"""
Refresh tracked game prices (Steam + best third-party via CheapShark).

Works without Redis/Celery — useful for local testing:

    python manage.py refresh_prices
    python manage.py refresh_prices --game-id 1
"""

from django.core.management.base import BaseCommand
from apps.games.models import Game
from apps.games.tasks import refresh_one_game, refresh_all_tracked_prices


class Command(BaseCommand):
    help = "Refresh tracked Steam + third-party price snapshots"

    def add_arguments(self, parser):
        parser.add_argument("--game-id", type=int, default=None)
        parser.add_argument("--country", default="GB")
        parser.add_argument(
            "--async",
            action="store_true",
            dest="run_async",
            help="Queue via Celery (requires Redis + worker)",
        )

    def handle(self, *args, **options):
        country = options["country"]
        if options["run_async"]:
            if options["game_id"]:
                from apps.games.tasks import refresh_single_game

                refresh_single_game.delay(options["game_id"], country=country)
                self.stdout.write(self.style.SUCCESS("Queued single game refresh."))
            else:
                refresh_all_tracked_prices.delay(country=country)
                self.stdout.write(self.style.SUCCESS("Queued full refresh."))
            return

        if options["game_id"]:
            game = Game.objects.get(pk=options["game_id"])
            r = refresh_one_game(game, country=country)
            self.stdout.write(str(r))
        else:
            summary = refresh_all_tracked_prices(country=country)
            self.stdout.write(self.style.SUCCESS(str(summary)))
