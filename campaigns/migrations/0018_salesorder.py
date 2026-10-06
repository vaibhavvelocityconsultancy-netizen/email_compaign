import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0017_quotation_cpo_document"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SalesOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("so_number", models.CharField(max_length=50, unique=True)),
                ("so_date", models.DateField()),
                ("subtotal", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("discount_percentage", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("discount_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("taxable_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("tax_percentage", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("tax_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("cgst_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("sgst_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("igst_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("packing_charges", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("total_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("tax_type", models.CharField(blank=True, max_length=30)),
                ("payment_terms", models.TextField(blank=True)),
                ("delivery_terms", models.TextField(blank=True)),
                ("remarks", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("CONFIRMED", "Confirmed"), ("IN_PROGRESS", "In Progress"), ("COMPLETED", "Completed"), ("CANCELLED", "Cancelled")], default="DRAFT", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sales_orders", to="campaigns.company")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_sales_orders", to=settings.AUTH_USER_MODEL)),
                ("quotation", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sales_orders", to="campaigns.quotation")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
