"""Track quote confirmation time separately from compact history events."""

from django.db import migrations, models
from django.db.models import F
from django.utils import timezone


def copy_recorded_time(apps, schema_editor):
    PriceRecord = apps.get_model("games", "PriceRecord")
    PriceRecord.objects.update(last_checked_at=F("recorded_at"))


class Migration(migrations.Migration):
    dependencies = [("games", "0006_expand_offer_urls")]

    operations = [
        migrations.AddField(
            model_name="pricerecord",
            name="last_checked_at",
            field=models.DateTimeField(null=True),
        ),
        migrations.RunPython(copy_recorded_time, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="pricerecord",
            name="last_checked_at",
            field=models.DateTimeField(default=timezone.now),
        ),
    ]
