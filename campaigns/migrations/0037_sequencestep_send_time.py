from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("campaigns", "0036_rename_campaigns_s_level_b8b3ad_idx_campaigns_s_level_851842_idx_and_more")]

    operations = [
        migrations.AddField(
            model_name="sequencestep",
            name="send_time",
            field=models.TimeField(blank=True, null=True),
        ),
    ]
