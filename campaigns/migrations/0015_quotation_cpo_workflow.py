from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0014_quotation_cpo_created"),
    ]

    operations = [
        migrations.RenameField(
            model_name="quotation",
            old_name="cpo_created",
            new_name="cpo_ready",
        ),
        migrations.AddField(
            model_name="quotation",
            name="customer_po_number",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="quotation",
            name="customer_po_document",
            field=models.FileField(
                blank=True,
                upload_to="quotations/customer_pos/",
            ),
        ),
    ]
