from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0016_quotation_cpo_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="quotation",
            name="cpo_document",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="quotations/customer_pos/",
            ),
        ),
    ]
