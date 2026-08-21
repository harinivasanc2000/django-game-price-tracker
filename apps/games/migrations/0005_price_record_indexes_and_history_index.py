"""Add indexes used by price history, drawer, and alert queries."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("games", "0004_watch_pricealert")]

    operations = [
        migrations.RenameIndex(
            model_name="pricealert",
            new_name="games_price_is_sent_2f2762_idx",
            old_name="games_price_is_sent_created_idx",
        ),
        migrations.RenameIndex(
            model_name="watch",
            new_name="games_watch_game_id_0f9136_idx",
            old_name="games_watch_game_id_user_idx",
        ),
        migrations.AlterField(
            model_name="browsehistory",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        migrations.AddIndex(
            model_name="browsehistory",
            index=models.Index(fields=["session_key", "-created_at"], name="games_brows_session_6cbb11_idx"),
        ),
        migrations.AddIndex(
            model_name="pricerecord",
            index=models.Index(fields=["game", "-recorded_at"], name="games_price_game_id_d971e7_idx"),
        ),
        migrations.AddIndex(
            model_name="pricerecord",
            index=models.Index(fields=["-recorded_at"], name="games_price_recorde_825bd9_idx"),
        ),
    ]
