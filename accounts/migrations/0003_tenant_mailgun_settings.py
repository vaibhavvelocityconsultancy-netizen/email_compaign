from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_tenant_user_tenant"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantMailgunSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("default_from_email", models.CharField(max_length=320)),
                ("sender_domain", models.CharField(max_length=255)),
                ("encrypted_api_key", models.TextField(blank=True)),
                ("encrypted_webhook_signing_key", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mailgun_settings",
                        to="accounts.tenant",
                    ),
                ),
            ],
        ),
    ]
