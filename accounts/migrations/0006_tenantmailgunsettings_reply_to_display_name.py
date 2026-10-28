from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_tenantmailgunsettings_reply_to_email")]

    operations = [
        migrations.AlterField(
            model_name="tenantmailgunsettings",
            name="reply_to_email",
            field=models.CharField(blank=True, default="", max_length=320),
        ),
    ]
