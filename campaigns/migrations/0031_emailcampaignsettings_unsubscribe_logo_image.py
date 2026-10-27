from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0030_emailcampaignsettings_unsubscribe_branding"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailcampaignsettings",
            name="unsubscribe_logo",
            field=models.ImageField(blank=True, null=True, upload_to="unsubscribe_logos/"),
        ),
    ]
