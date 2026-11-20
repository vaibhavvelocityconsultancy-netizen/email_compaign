from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0044_lead_status_failed"),
    ]

    operations = [
        migrations.AlterField(
            model_name="batch",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("paused", "Paused"),
                    ("completed", "Completed"),
                    ("inactive", "Inactive"),
                ],
                default="active",
                max_length=20,
            ),
        ),
    ]
