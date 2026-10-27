from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0029_emailcampaignsettings_unique_email_campaign_settings_per_tenant_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailcampaignsettings",
            name="unsubscribe_company_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="emailcampaignsettings",
            name="unsubscribe_support_email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
        migrations.AddField(
            model_name="emailcampaignsettings",
            name="unsubscribe_company_address",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="emailcampaignsettings",
            name="unsubscribe_brand_color",
            field=models.CharField(blank=True, default="", max_length=7),
        ),
        migrations.AddField(
            model_name="emailcampaignsettings",
            name="unsubscribe_logo_url",
            field=models.URLField(blank=True, default="", max_length=500),
        ),
    ]
