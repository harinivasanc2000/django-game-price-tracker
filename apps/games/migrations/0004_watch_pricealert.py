from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0003_adminchangelog_sitesettings_game_admin_notes_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Watch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "target_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Optional: alert me when the GBP price drops below this",
                        max_digits=10,
                        null=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "game",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="watches",
                        to="games.game",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="watches",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="PriceAlert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("currency", models.CharField(default="GBP", max_length=3)),
                ("target_price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("store", models.CharField(blank=True, max_length=120)),
                ("url", models.URLField(blank=True)),
                ("is_sent", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                (
                    "watch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="alerts",
                        to="games.watch",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="watch",
            index=models.Index(fields=["game", "user"], name="games_watch_game_id_user_idx"),
        ),
        migrations.AddConstraint(
            model_name="watch",
            constraint=models.UniqueConstraint(fields=("user", "game"), name="unique_user_game_watch"),
        ),
        migrations.AddIndex(
            model_name="pricealert",
            index=models.Index(fields=["is_sent", "-created_at"], name="games_price_is_sent_created_idx"),
        ),
    ]
