from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0018_salesorder"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesorder",
            name="so_pdf",
            field=models.FileField(blank=True, null=True, upload_to="sales_orders/"),
        ),
    ]
