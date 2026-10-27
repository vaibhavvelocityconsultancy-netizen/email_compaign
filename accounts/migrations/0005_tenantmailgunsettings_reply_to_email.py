from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_merge_20261026_1243"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantmailgunsettings",
            name="reply_to_email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
    ]
