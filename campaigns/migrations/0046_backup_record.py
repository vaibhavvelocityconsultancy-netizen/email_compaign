import uuid
from datetime import timedelta

from django.conf import settings
from django.core import serializers
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def backfill_existing_soft_deleted(apps, schema_editor):
    BackupRecord = apps.get_model("campaigns", "BackupRecord")
    database = schema_editor.connection.alias
    models_to_backup = [
        ("Lead", "Leads", {"is_active": True}, {"is_active": False}),
        ("Opportunity", "Opportunities", {"is_active": True}, {"is_active": False}),
        ("CompanyContact", "Companies", {"is_active": True}, {"is_active": False}),
        ("Task", "Tasks", {"is_deleted": False}, {"is_deleted": True}),
        ("Batch", "Email campaigns", {"status": "paused"}, {"status": "inactive"}),
    ]
    now = django.utils.timezone.now()
    for model_name, module, restore_fields, filters in models_to_backup:
        model = apps.get_model("campaigns", model_name)
        for instance in model.objects.using(database).filter(**filters).iterator():
            tenant_id = getattr(instance, "tenant_id", None)
            if tenant_id is None:
                related = getattr(instance, "company", None)
                tenant_id = getattr(related, "tenant_id", None)
            BackupRecord.objects.using(database).create(
                deletion_group=uuid.uuid4(),
                module=module,
                model_label=instance._meta.label_lower,
                object_id=str(instance.pk),
                record_name=str(instance)[:255],
                payload=serializers.serialize("json", [instance]),
                restore_fields=restore_fields,
                tenant_id=tenant_id,
                deleted_at=now,
                expires_at=now + timedelta(days=30),
            )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_tenantmailgunsettings_reply_to_display_name"),
        ("campaigns", "0045_batch_status_inactive"),
    ]

    operations = [
        migrations.CreateModel(
            name="BackupRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("deletion_group", models.UUIDField(db_index=True, default=uuid.uuid4)),
                ("module", models.CharField(db_index=True, max_length=80)),
                ("model_label", models.CharField(max_length=120)),
                ("object_id", models.CharField(max_length=64)),
                ("record_name", models.CharField(blank=True, max_length=255)),
                ("payload", models.TextField()),
                ("restore_fields", models.JSONField(blank=True, default=dict)),
                ("deleted_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("restored_at", models.DateTimeField(blank=True, null=True)),
                ("deleted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="deleted_backup_records", to=settings.AUTH_USER_MODEL)),
                ("tenant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="backup_records", to="accounts.tenant")),
            ],
            options={"ordering": ["-deleted_at", "-id"]},
        ),
        migrations.RunPython(
            backfill_existing_soft_deleted,
            migrations.RunPython.noop,
        ),
    ]
