import json

from django.db import migrations, models


def backfill_tenant_names(apps, schema_editor):
    BackupRecord = apps.get_model("campaigns", "BackupRecord")
    database = schema_editor.connection.alias
    records = list(BackupRecord.objects.using(database).select_related("tenant"))
    deleted_tenant_names = {}
    for record in records:
        if record.model_label != "accounts.tenant":
            continue
        try:
            tenant_fields = json.loads(record.payload)[0]["fields"]
        except (IndexError, KeyError, TypeError, json.JSONDecodeError):
            continue
        deleted_tenant_names[record.deletion_group] = tenant_fields.get("name", "")

    for record in records:
        if record.tenant_id:
            record.tenant_name = record.tenant.name
        elif record.deletion_group in deleted_tenant_names:
            record.tenant_name = deleted_tenant_names[record.deletion_group]
        if record.tenant_name:
            record.save(update_fields=["tenant_name"], using=database)


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0046_backup_record"),
    ]

    operations = [
        migrations.AddField(
            model_name="backuprecord",
            name="tenant_name",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.RunPython(backfill_tenant_names, migrations.RunPython.noop),
    ]
