from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("campaigns", "0037_sequencestep_send_time")]

    operations = [
        migrations.AddField(
            model_name="inboundreply",
            name="external_source_key",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddConstraint(
            model_name="inboundreply",
            constraint=models.UniqueConstraint(
                condition=models.Q(("external_source_key__isnull", False)),
                fields=("tenant", "external_source_key"),
                name="unique_reply_source_key_per_tenant",
            ),
        ),
        migrations.CreateModel(
            name="IonosMailbox",
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
                ("email", models.EmailField(blank=True, max_length=254)),
                ("encrypted_password", models.TextField(blank=True)),
                ("is_connected", models.BooleanField(default=False)),
                ("uid_validity", models.CharField(blank=True, max_length=64)),
                ("last_uid", models.PositiveBigIntegerField(default=0)),
                ("last_sync_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="accounts.tenant",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant",),
                        name="unique_ionos_mailbox_per_tenant",
                    )
                ]
            },
        ),
    ]
