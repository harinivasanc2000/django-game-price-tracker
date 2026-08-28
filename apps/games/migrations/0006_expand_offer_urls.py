from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("games", "0005_price_record_indexes_and_history_index"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pricealert",
            name="url",
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AlterField(
            model_name="pricerecord",
            name="url",
            field=models.URLField(blank=True, max_length=1000),
        ),
    ]
