from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.utils import timezone
import os

LICENCE_PRESETS = [
    ("driver_licence", "Driver Licence"),
    ("bus_licence", "Bus Licence"),
    ("passport", "Passport"),
    ("blue_card", "Blue Card"),
    ("forklift_licence", "Forklift Licence"),
    ("additional", "Additional Licence"),
]

LICENCE_PRESET_LABELS = dict(LICENCE_PRESETS)

class Form(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
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
    
def upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    return f"credentials/{instance.user_id}/{instance.title}{ext}"

class Credential(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="credentials",
    )
    title = models.CharField(max_length=200)
    licence_number = models.CharField(max_length=20, blank=True, default="")
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    required = models.BooleanField(default=False)
    image = models.ImageField(upload_to=upload_path, null=True, blank=True)

    @property
    def status(self):
        if not self.issue_date or not self.expiry_date:
            return "TBA"
        return "Expired" if self.expiry_date < timezone.localdate() else "Compliant"

    @property
    def is_additional(self):
        preset_titles = {
            "Driver Licence",
            "Bus Licence",
            "Passport",
            "Blue Card",
            "Forklift Licence",
            "Site Induction",
            "Medical",
            "Photo ID",
        }
        return self.title not in preset_titles

    def __str__(self):
        return f"{self.title} ({'Required' if self.required else 'Optional'})"

    
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
        ('licence_upload', 'Licence Image Upload'),
    ]
    
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField(default=" ")
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='text')
    options_text = models.TextField(blank=True, null=True, help_text="For multiple choice or licence label")
    is_required = models.BooleanField(default=True)
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.form.title} - {self.question_text[:50]}"
    
    @property
    def options(self):
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
    form = models.ForeignKey(Form, 
                             on_delete=models.CASCADE, 
                             related_name='submissions',
                             )
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='form_submissions'
        )
    
    submitted_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.email} - {self.form.title} - {self.submitted_at}"
    

class FormDraft(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete = models.CASCADE,
        related_name="form_drafts",        
    )
    
    invite = models.ForeignKey(
        "ProjectInvite",
        on_delete=models.CASCADE,
        related_name="form_drafts"
    )
    
    answers_json = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ("user", "invite")
class Answer(models.Model):
    submission = models.ForeignKey(FormSubmission, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    answer_text = models.TextField(blank=True)
    answer_file = models.ImageField(upload_to="form_answers/%Y/%m/", null=True, blank=True)
    
    def __str__(self):
        return f"{self.submission.user.email} - {self.question.question_text[:30]}"

class SubmissionCredentialAttachment(models.Model):
    submission = models.ForeignKey(
        FormSubmission,
        on_delete=models.CASCADE,
        related_name="attached_credentials",
    )
    source_credential = models.ForeignKey(
        Credential,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submission_copies",
    )
    title = models.CharField(max_length=200)
    image = models.ImageField(upload_to="submission_credential_copies/%Y/%m/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.submission.user.email} - {self.title}"

class Project(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_projects",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_indefinite(self):
        return self.end_date is None

    def __str__(self):
        return self.title


class ProjectRole(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="roles")
    title = models.CharField(max_length=200)
    required_form = models.ForeignKey(
        Form,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="project_roles",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["project", "title"]
        ordering = ["title"]

    def __str__(self):
        return f"{self.project.title} - {self.title}"


class ProjectInvite(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("viewed", "Viewed"),
        ("completed", "Completed"),
        ("declined", "Declined"),
    ]

    REVIEW_STATUS_CHOICES = [
        ("pending_review", "Pending Review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="invites")
    project_role = models.ForeignKey(
        ProjectRole,
        on_delete=models.CASCADE,
        related_name="invites",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_invites",
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="project_invites_sent",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    review_status = models.CharField(
        max_length=20,
        choices=REVIEW_STATUS_CHOICES,
        default="pending_review",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="project_invites_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    allow_reapply = models.BooleanField(default=False)
    invited_at = models.DateTimeField(auto_now_add=True)
    viewed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ["project_role", "user"]
        ordering = ["-invited_at"]

    def __str__(self):
        return f"{self.user.email} invited to {self.project.title} as {self.project_role.title}"
    
def approval_document_upload_path(instance, filename):
    return f"approval_documents/{instance.project_id}/{filename}"


class ApprovalDocument(models.Model):
    SCOPE_CHOICES = [
        ("project", "Project"),
        ("role", "Role"),
        ("user", "User"),
    ]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="approval_documents",
    )
    role = models.ForeignKey(
        ProjectRole,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="approval_documents",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="approval_documents",
    )
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES)
    title = models.CharField(max_length=255)
    document = models.FileField(upload_to=approval_document_upload_path)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_approval_documents",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scope", "title"]

    def __str__(self):
        return f"{self.project.title} - {self.title} ({self.scope})"

class OnboardingInvite(models.Model):
    
    STATUS_CHOICES = [
        ("sent", "Sent"),
        ("account_created", "Account Created"),
        ("default_form_pending", "Default Form Pending"),
        ("completed", "Completed"),
        ("expired", "Expired"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="onboarding_invites",
        null=True,
        blank=True,
    )
    email = models.EmailField()
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    token = models.CharField(max_length=255, unique=True)
    requires_default_form = models.BooleanField(default=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="sent")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.email} - {self.status}"
    
class CredentialNotification(models.Model):
    REMINDER_BAND_CHOICES = [
        ("6_month", "6 Months"),
        ("1_month", "1 Month"),
        ("2_week", "2 Weeks"),
        ("1_week", "1 Week"),
        ("3_day", "3 Days"),
        ("expired", "Expired"),
    ]

    credential = models.ForeignKey(
        Credential,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    reminder_band = models.CharField(max_length=20, choices=REMINDER_BAND_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["credential", "reminder_band"]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.credential} - {self.reminder_band}"
    
class LicenceRenewalRequest(models.Model):
    credential = models.ForeignKey(
        Credential,
        on_delete=models.CASCADE,
        related_name="renewal_requests",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="licence_renewal_requests",
    )
    token = models.CharField(max_length=255, unique=True)
    reminder_band = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    is_used = models.BooleanField(default=False)
    renewal_image = models.ImageField(upload_to="renewal_uploads/", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.credential.title} - {self.reminder_band}"
    
