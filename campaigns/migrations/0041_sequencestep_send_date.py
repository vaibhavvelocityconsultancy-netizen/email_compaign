from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0040_backfill_auto_generated_sequences"),
    ]

    operations = [
        migrations.AddField(
            model_name="sequencestep",
            name="send_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
