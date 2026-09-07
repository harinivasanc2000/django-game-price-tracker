from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("games", "0007_price_record_last_checked"),
    ]

    operations = [
        migrations.CreateModel(
            name="OwnedGame",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("platform", models.CharField(choices=[("ps4", "PlayStation 4"), ("ps5", "PlayStation 5"), ("pc", "PC"), ("xbox", "Xbox"), ("switch", "Nintendo Switch"), ("other", "Other")], default="ps4", max_length=20)),
                ("purchase_price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("currency", models.CharField(default="GBP", max_length=3)),
                ("retailer", models.CharField(blank=True, max_length=120)),
                ("location", models.CharField(blank=True, max_length=120)),
                ("purchased_on", models.DateField(blank=True, null=True)),
                ("completed", models.BooleanField(default=False)),
                ("notes", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="owned_games", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["completed", "-purchased_on", "title"]},
        ),
        migrations.AddConstraint(
            model_name="ownedgame",
            constraint=models.UniqueConstraint(fields=("user", "title", "platform"), name="unique_user_owned_game"),
        ),
        migrations.AddConstraint(
            model_name="ownedgame",
            constraint=models.CheckConstraint(condition=models.Q(("purchase_price__gte", 0)), name="owned_game_price_nonnegative"),
        ),
        migrations.AddIndex(
            model_name="ownedgame",
            index=models.Index(fields=["user", "platform", "completed"], name="games_owned_user_id_00d38e_idx"),
        ),
    ]
