from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0043_lead_status_completed"),
    ]

    operations = [
        migrations.AlterField(
            model_name="lead",
            name="status",
            field=models.CharField(
                choices=[
                    ("NEW", "New"),
                    ("ACTIVE", "Active"),
                    ("JUNK", "Junk"),
                    ("HOT", "Hot"),
                    ("COLD", "Cold"),
                    ("OTHER", "Other"),
                    ("COMPLETED", "Completed"),
                    ("FAILED", "Failed"),
                ],
                default="NEW",
                max_length=20,
            ),
        ),
    ]
