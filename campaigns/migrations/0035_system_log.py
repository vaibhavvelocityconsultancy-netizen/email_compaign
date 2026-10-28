from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("campaigns", "0034_email_signatures"),
    ]

    operations = [
        migrations.CreateModel(
            name="SystemLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("level", models.CharField(max_length=10)),
                ("logger_name", models.CharField(max_length=255)),
                ("module", models.CharField(blank=True, max_length=255)),
                ("message", models.TextField()),
                ("source", models.CharField(blank=True, max_length=255)),
                ("is_notification", models.BooleanField(default=False)),
                ("is_read", models.BooleanField(default=False)),
                ("is_acknowledged", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="system_logs", to="accounts.tenant")),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["level", "created_at"], name="campaigns_s_level_b8b3ad_idx"),
                    models.Index(fields=["is_notification", "is_read", "created_at"], name="campaigns_s_is_noti_c9c3d_idx"),
                ],
            },
        ),
    ]
