from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0012_add_licence_number_to_credential"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectinvite",
            name="rejection_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="projectinvite",
            name="allow_reapply",
            field=models.BooleanField(default=False),
        ),
    ]