from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.utils import timezone

class Form(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)  # Add this line
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_forms')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.title

class WorkerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="worker_profile"
    )
    dob = models.DateField(null=True, blank=True)
    role = models.CharField(max_length=200, blank=True)
    project = models.CharField(max_length=200, blank=True)
    employer = models.CharField(max_length=200, blank=True)
    emergency_contact_name = models.CharField(max_length=200, blank=True)
    emergency_contact_mobile = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"Profile for {self.user.get_full_name() or self.user.email}"
    

class Credential(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="credentials",
    )
    title = models.CharField(max_length=200)
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    required = models.BooleanField(default=False)

    @property
    def status(self):
        if not self.issue_date or not self.expiry_date:
            return "TBA"
        return "Expired" if self.expiry_date < timezone.localdate() else "Compliant"

    def __str__(self):
        return f"{self.title} ({'Required' if self.required else 'Optional'})"

class Question(models.Model):
    form = models.ForeignKey(
        Form,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    text = models.CharField(max_length=500)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Q{self.order}: {self.text[:50]}"
    
class Question(models.Model):
    QUESTION_TYPES = [
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
    ]
    
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField(default=" ")
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='text')
    options_text = models.TextField(blank=True, null=True, help_text="For multiple choice: one option per line")
    is_required = models.BooleanField(default=True)
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.form.title} - {self.question_text[:50]}"
    
    @property
    def options(self):
        """Split options_text into a list"""
        if self.options_text:
            return [opt.strip() for opt in self.options_text.split('\n') if opt.strip()]
        return []

class FormAssignment(models.Model):
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name='assignments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='assigned_forms')
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='forms_assigned_by_me')
    due_date = models.DateTimeField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['form', 'user']
    
    def __str__(self):
        return f"{self.form.title} → {self.user.email}"

class FormSubmission(models.Model):
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name='submissions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='form_submissions')
    submitted_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.email} - {self.form.title} - {self.submitted_at}"

class Answer(models.Model):
    submission = models.ForeignKey(FormSubmission, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    answer_text = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.submission.user.email} - {self.question.question_text[:30]}"