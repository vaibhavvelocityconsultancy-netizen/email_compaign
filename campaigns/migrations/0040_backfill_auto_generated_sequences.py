from django.db import migrations


def mark_auto_generated_sequences(apps, schema_editor):
    Sequence = apps.get_model("campaigns", "Sequence")
    Sequence.objects.filter(name__endswith=" - One-time email").update(
        is_auto_generated=True
    )


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0039_sequence_is_auto_generated"),
    ]

    operations = [
        migrations.RunPython(mark_auto_generated_sequences, migrations.RunPython.noop),
    ]
