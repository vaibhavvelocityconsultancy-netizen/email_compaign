from django.db import migrations


def convert_message_template_to_utf8mb4(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return

    template_model = apps.get_model("campaigns", "MessageTemplate")
    table_name = schema_editor.quote_name(template_model._meta.db_table)
    schema_editor.execute(
        f"ALTER TABLE {table_name} MODIFY body LONGTEXT "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL"
    )


class Migration(migrations.Migration):
    # MyISAM cannot roll back DDL, so Django must not wrap this ALTER TABLE
    # statement in a transaction.
    atomic = False

    dependencies = [
        ("campaigns", "0041_sequencestep_send_date"),
    ]

    operations = [
        migrations.RunPython(convert_message_template_to_utf8mb4, migrations.RunPython.noop),
    ]
