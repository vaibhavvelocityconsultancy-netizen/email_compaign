from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0015_quotation_cpo_workflow"),
    ]

    operations = [
        migrations.RenameField(
            model_name="quotation",
            old_name="cpo_ready",
            new_name="cpo_created",
        ),
        migrations.RemoveField(
            model_name="quotation",
            name="customer_po_number",
        ),
        migrations.RemoveField(
            model_name="quotation",
            name="customer_po_document",
        ),
        migrations.AddField(
            model_name="quotation",
            name="cpo_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
