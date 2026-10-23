from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0024_inboundreply"),
    ]

    operations = [
        migrations.CreateModel(
            name="GmailMailbox",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("encrypted_credentials", models.TextField(blank=True)),
                ("history_id", models.CharField(blank=True, max_length=64)),
                ("last_sync_at", models.DateTimeField(blank=True, null=True)),
                ("oauth_state_hash", models.CharField(blank=True, max_length=64)),
                (
                    "oauth_state_created_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
