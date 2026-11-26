from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("campaigns", "0047_backup_tenant_name")]

    operations = [
        migrations.AddField(
            model_name="state",
            name="iso_code",
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
        migrations.AddConstraint(
            model_name="state",
            constraint=models.UniqueConstraint(
                condition=models.Q(("iso_code__isnull", False)),
                fields=("tenant", "country", "iso_code"),
                name="unique_state_iso_code_per_tenant_country",
            ),
        ),
    ]
