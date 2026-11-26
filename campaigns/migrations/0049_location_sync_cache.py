from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0048_state_iso_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="country",
            name="states_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="state",
            name="cities_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
