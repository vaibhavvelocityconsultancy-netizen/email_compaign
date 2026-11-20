from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0042_message_template_utf8mb4"),
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
                ],
                default="NEW",
                max_length=20,
            ),
        ),
    ]
