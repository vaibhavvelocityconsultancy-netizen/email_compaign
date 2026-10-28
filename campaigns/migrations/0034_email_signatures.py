from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0033_lead_categories"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmailSignature",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("text", models.TextField(blank=True)),
                ("logo", models.ImageField(blank=True, null=True, upload_to="email_signature_logos/")),
                ("is_default", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.tenant")),
            ],
            options={"ordering": ["-is_default", "name"]},
        ),
        migrations.AddConstraint(
            model_name="emailsignature",
            constraint=models.UniqueConstraint(condition=models.Q(is_default=True), fields=("tenant",), name="unique_default_email_signature_per_tenant"),
        ),
        migrations.AddField(
            model_name="messagetemplate",
            name="signature_profile",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="templates", to="campaigns.emailsignature"),
        ),
    ]
