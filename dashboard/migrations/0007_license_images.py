from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0006_projects"),
    ]

    operations = [
        migrations.AddField(
            model_name="credential",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="credentials/%Y/%m/"),
        ),
        migrations.AddField(
            model_name="answer",
            name="answer_file",
            field=models.ImageField(blank=True, null=True, upload_to="form_answers/%Y/%m/"),
        ),
        migrations.AlterField(
            model_name="question",
            name="question_type",
            field=models.CharField(
                choices=[
                    ('text', 'Short Text'),
                    ('textarea', 'Long Text'),
                    ('number', 'Number'),
                    ('date', 'Date'),
                    ('time', 'Time'),
                    ('email', 'Email'),
                    ('phone', 'Phone Number'),
                    ('radio', 'Multiple Choice (Single)'),
                    ('checkbox', 'Multiple Choice (Multiple)'),
                    ('dropdown', 'Dropdown'),
                    ('file', 'File Upload'),
                    ('license_upload', 'Licence Image Upload'),
                ],
                default='text',
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="SubmissionCredentialAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("image", models.ImageField(upload_to="submission_credential_copies/%Y/%m/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "source_credential",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="submission_copies",
                        to="dashboard.credential",
                    ),
                ),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attached_credentials",
                        to="dashboard.formsubmission",
                    ),
                ),
            ],
        ),
    ]