from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.utils import timezone

class Form(models.Model):
    title = models.CharField(max_length=200, default="Untitled Form")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="forms",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} (by {self.created_by})"


class Question(models.Model):
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()

    # --- add these fields ---
    QUESTION_TYPES = [
        ("text", "Open text"),
        ("mcq", "Multiple choice"),
        ("dropdown", "Dropdown"),
    ]
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default="text")
    # For mcq/dropdown, store one option per line:
    options_text = models.TextField(blank=True, default="",
                                    help_text="For multiple choice / dropdown, enter one option per line.")

    order = models.PositiveIntegerField(default=0)  # (optional) if you already have this, keep your version

    class Meta:
        ordering = ["order", "id"]

    # --- helpers ---
    def options(self):
        """Return list of non-empty options, trimmed."""
        if not self.options_text:
            return []
        return [o.strip() for o in self.options_text.splitlines() if o.strip()] 

class FormAssignment(models.Model):
    form = models.ForeignKey('dashboard.Form', on_delete=models.CASCADE, related_name='assignments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='form_assignments')
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_forms')
    assigned_at = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('form', 'user')
        indexes = [
            models.Index(fields=['form', 'user']),
            models.Index(fields=['form', 'completed']),
        ]

    def mark_completed(self):
        if not self.completed:
            self.completed = True
            self.completed_at = timezone.now()
            self.save()

class FormSubmission(models.Model):
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="submissions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="form_submissions")
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("form", "user")  # one submission per user per form
        indexes = [
            models.Index(fields=["form", "user"]),
        ]

    def __str__(self):
        return f"Submission: {self.user} → {self.form} @ {self.submitted_at:%Y-%m-%d %H:%M}"


class Answer(models.Model):
    submission = models.ForeignKey(FormSubmission, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    value = models.TextField(blank=True, default="")  # generic text answer

    class Meta:
        unique_together = ("submission", "question")
        indexes = [
            models.Index(fields=["question"]),
        ]

    def __str__(self):
        return f"Ans[{self.question_id}] by {self.submission.user_id}"