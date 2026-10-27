from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_tenantmailgunsettings_reply_to_email"),
        ("campaigns", "0032_globalize_unsubscribe_page_settings"),
    ]

    operations = [
        migrations.CreateModel(
            name="LeadCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.tenant")),
            ],
        ),
        migrations.AddConstraint(
            model_name="leadcategory",
            constraint=models.UniqueConstraint(fields=("tenant", "name"), name="unique_lead_category_per_tenant"),
        ),
        migrations.AddField(
            model_name="lead",
            name="category",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="leads", to="campaigns.leadcategory"),
        ),
        migrations.AddField(
            model_name="messagetemplate",
            name="category",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="message_templates", to="campaigns.leadcategory"),
        ),
        migrations.AddField(
            model_name="batch",
            name="category",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="batches", to="campaigns.leadcategory"),
        ),
    ]
