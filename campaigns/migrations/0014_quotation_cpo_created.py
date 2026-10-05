from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0013_quotation_company"),
    ]

    operations = [
        migrations.AddField(
            model_name="quotation",
            name="cpo_created",
            field=models.BooleanField(default=False),
        ),
    ]
