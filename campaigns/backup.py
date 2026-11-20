from datetime import timedelta
import uuid

from django.apps import apps
from django.core import serializers
from django.db import transaction
from django.db.models.deletion import Collector
from django.utils import timezone

from .models import BackupRecord

RETENTION_DAYS = 30
MODEL_MODULES = {
    "accounts.tenant": "Tenants",
    "accounts.user": "Users",
    "accounts.role": "User & Roles",
    "accounts.module": "User & Roles",
    "accounts.rolepermission": "User & Roles",
    "campaigns.company": "Companies",
    "campaigns.companycontact": "Companies",
    "campaigns.lead": "Leads",
    "campaigns.leadcategory": "Leads",
    "campaigns.opportunity": "Opportunities",
    "campaigns.opportunitymodule": "Opportunities",
    "campaigns.quotation": "Quotations",
    "campaigns.quotationitem": "Quotations",
    "campaigns.salesorder": "Sales orders",
    "campaigns.task": "Tasks",
    "campaigns.taskattachment": "Tasks",
    "campaigns.batch": "Email campaigns",
    "campaigns.batchlead": "Email campaigns",
    "campaigns.messagelog": "Email campaign logs",
    "campaigns.inboundreply": "Email campaign replies",
    "campaigns.messagetemplate": "Email templates",
    "campaigns.emailsignature": "Email signatures",
    "campaigns.sequence": "Email sequences",
    "campaigns.sequencestep": "Email sequences",
    "campaigns.country": "Locations",
    "campaigns.state": "Locations",
    "campaigns.city": "Locations",
    "campaigns.systemlog": "System logs",
}


def _tenant_id_for(instance, fallback=None):
    tenant_id = getattr(instance, "tenant_id", None)
    if tenant_id:
        return tenant_id
    for field in instance._meta.concrete_fields:
        if not field.is_relation or not field.many_to_one:
            continue
        related = getattr(instance, field.name, None)
        if related is not None:
            tenant_id = getattr(related, "tenant_id", None)
            if tenant_id:
                return tenant_id
    return fallback


def _tenant_name_for(instance, fallback="", visited=None):
    visited = visited or set()
    identity = (instance._meta.label_lower, str(instance.pk))
    if identity in visited:
        return fallback
    visited.add(identity)
    if instance._meta.label_lower == "accounts.tenant":
        return getattr(instance, "name", "")
    tenant = getattr(instance, "tenant", None)
    if tenant is not None:
        return getattr(tenant, "name", "") or fallback
    for field in instance._meta.concrete_fields:
        if not field.is_relation or not field.many_to_one:
            continue
        related = getattr(instance, field.name, None)
        if related is not None:
            name = _tenant_name_for(related, fallback, visited)
            if name:
                return name
    return fallback


def archive_before_delete(
    instance, request, module, restore_fields=None, restore_values=None
):
    purge_expired_backups()
    restore_fields = tuple(restore_fields or ())
    restore_values = restore_values or {}
    group_id = uuid.uuid4()
    deleted_at = timezone.now()
    objects = [instance]

    if not restore_fields:
        collector = Collector(using=instance._state.db)
        collector.collect([instance])
        objects = [
            obj
            for model, model_objects in collector.data.items()
            if not model._meta.auto_created
            for obj in model_objects
        ]
        if instance not in objects:
            objects.insert(0, instance)

    root_tenant = (
        instance
        if instance._meta.label_lower == "accounts.tenant"
        else getattr(instance, "tenant", None)
    )
    tenant_id = getattr(instance, "tenant_id", None) or getattr(
        root_tenant, "pk", None
    )
    tenant_name = getattr(root_tenant, "name", "")
    user = getattr(request, "user", None)
    deleted_by = user if getattr(user, "is_authenticated", False) else None
    entries = []
    for obj in objects:
        fields_to_restore = (
            {field: getattr(obj, field) for field in restore_fields}
            if obj.pk == instance.pk and obj.__class__ is instance.__class__
            else {}
        )
        if fields_to_restore:
            fields_to_restore.update(restore_values)
        try:
            record_name = str(obj)[:255]
        except Exception:
            record_name = f"{obj._meta.verbose_name} #{obj.pk}"
        record_tenant_name = _tenant_name_for(obj, tenant_name)
        entries.append(
            BackupRecord(
                deletion_group=group_id,
                module=MODEL_MODULES.get(obj._meta.label_lower, module),
                model_label=obj._meta.label_lower,
                object_id=str(obj.pk),
                record_name=record_name,
                payload=serializers.serialize("json", [obj]),
                restore_fields=fields_to_restore,
                tenant_id=_tenant_id_for(obj, tenant_id),
                tenant_name=record_tenant_name,
                deleted_by=deleted_by,
                deleted_at=deleted_at,
                expires_at=deleted_at + timedelta(days=RETENTION_DAYS),
            )
        )
    BackupRecord.objects.bulk_create(entries)
    return group_id


@transaction.atomic
def archive_and_delete_queryset(queryset, request, module):
    instances = list(queryset)
    for instance in instances:
        archive_before_delete(instance, request, module)
    for instance in instances:
        instance.delete()
    return len(instances)


@transaction.atomic
def restore_backup_group(group_id):
    records = list(
        BackupRecord.objects.select_for_update().filter(
            deletion_group=group_id,
            restored_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
    )
    if not records:
        raise ValueError("This backup has expired or has already been restored.")

    objects = {}
    for record in records:
        model = apps.get_model(record.model_label)
        deserialized = next(serializers.deserialize("json", record.payload))
        obj = deserialized.object
        key = (model._meta.label_lower, str(obj.pk))
        objects[key] = (record, deserialized)

    ordered_keys = []
    visited = set()

    def add_with_dependencies(key):
        if key in visited:
            return
        visited.add(key)
        _record, deserialized = objects[key]
        obj = deserialized.object
        for field in obj._meta.concrete_fields:
            if not field.is_relation or not field.remote_field:
                continue
            related_id = getattr(obj, field.attname, None)
            if related_id is None:
                continue
            dependency_key = (
                field.remote_field.model._meta.label_lower,
                str(related_id),
            )
            if dependency_key in objects:
                add_with_dependencies(dependency_key)
        ordered_keys.append(key)

    for key in objects:
        add_with_dependencies(key)

    with transaction.atomic():
        pending_m2m = []
        for key in ordered_keys:
            record, deserialized = objects[key]
            snapshot_obj = deserialized.object
            model = apps.get_model(record.model_label)
            manager = model._base_manager
            instance = manager.filter(pk=snapshot_obj.pk).first()

            if record.restore_fields:
                if instance is None:
                    deserialized.save(save_m2m=False)
                    pending_m2m.append(deserialized)
                    instance = snapshot_obj
                for field_name, value in record.restore_fields.items():
                    setattr(instance, field_name, value)
                instance.save(update_fields=list(record.restore_fields))
            elif instance is None:
                if record.model_label == "campaigns.batch":
                    snapshot_obj.status = "paused"
                deserialized.save(save_m2m=False)
                pending_m2m.append(deserialized)
            else:
                raise ValueError(
                    f"Cannot restore {record.record_name}: that record ID is already in use."
                )

        for deserialized in pending_m2m:
            for field_name, related_objects in (deserialized.m2m_data or {}).items():
                getattr(deserialized.object, field_name).set(related_objects)

        BackupRecord.objects.filter(pk__in=[record.pk for record in records]).update(
            restored_at=timezone.now()
        )
    return len(records)


def purge_expired_backups(now=None):
    now = now or timezone.now()
    expired_records = [
        record
        for record in BackupRecord.objects.filter(
            expires_at__lte=now,
            restored_at__isnull=True,
        )
        if record.restore_fields
    ]
    for record in expired_records:
        model = apps.get_model(record.model_label)
        model._base_manager.filter(pk=record.object_id).delete()
    return BackupRecord.objects.filter(expires_at__lte=now).delete()[0]
