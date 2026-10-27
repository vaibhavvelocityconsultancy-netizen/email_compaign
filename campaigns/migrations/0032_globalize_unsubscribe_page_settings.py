from django.db import migrations, models
from django.db.models import Q


def copy_latest_unsubscribe_settings(apps, schema_editor):
    EmailCampaignSettings = apps.get_model("campaigns", "EmailCampaignSettings")
    UnsubscribePageSettings = apps.get_model("campaigns", "UnsubscribePageSettings")
    database = schema_editor.connection.alias
    source = (
        EmailCampaignSettings.objects.using(database)
        .filter(
            Q(unsubscribe_company_name__gt="")
            | Q(unsubscribe_support_email__gt="")
            | Q(unsubscribe_company_address__gt="")
            | Q(unsubscribe_brand_color__gt="")
            | Q(unsubscribe_logo_url__gt="")
            | Q(unsubscribe_logo__gt="")
        )
        .order_by("-updated_at", "-pk")
        .first()
    )
    if source is None:
        return

    UnsubscribePageSettings.objects.using(database).update_or_create(
        pk=1,
        defaults={
            "unsubscribe_company_name": source.unsubscribe_company_name,
            "unsubscribe_support_email": source.unsubscribe_support_email,
            "unsubscribe_company_address": source.unsubscribe_company_address,
            "unsubscribe_brand_color": source.unsubscribe_brand_color,
            "unsubscribe_logo_url": source.unsubscribe_logo_url,
            "unsubscribe_logo": source.unsubscribe_logo.name,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0031_emailcampaignsettings_unsubscribe_logo_image"),
    ]

    operations = [
        migrations.CreateModel(
            name="UnsubscribePageSettings",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("unsubscribe_company_name", models.CharField(blank=True, default="", max_length=120)),
                ("unsubscribe_support_email", models.EmailField(blank=True, default="", max_length=254)),
                ("unsubscribe_company_address", models.CharField(blank=True, default="", max_length=255)),
                ("unsubscribe_brand_color", models.CharField(blank=True, default="", max_length=7)),
                ("unsubscribe_logo_url", models.URLField(blank=True, default="", max_length=500)),
                ("unsubscribe_logo", models.ImageField(blank=True, null=True, upload_to="unsubscribe_logos/")),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.RunPython(copy_latest_unsubscribe_settings, migrations.RunPython.noop),
        migrations.RemoveField(model_name="emailcampaignsettings", name="unsubscribe_company_name"),
        migrations.RemoveField(model_name="emailcampaignsettings", name="unsubscribe_support_email"),
        migrations.RemoveField(model_name="emailcampaignsettings", name="unsubscribe_company_address"),
        migrations.RemoveField(model_name="emailcampaignsettings", name="unsubscribe_brand_color"),
        migrations.RemoveField(model_name="emailcampaignsettings", name="unsubscribe_logo_url"),
        migrations.RemoveField(model_name="emailcampaignsettings", name="unsubscribe_logo"),
    ]
