from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.utils import timezone
import os

# Known licence preset keys and their human-readable labels.
# Used in the form builder and credential save logic to map select values to titles.
LICENCE_PRESETS = [
    ("driver_licence", "Driver Licence"),
    ("bus_licence", "Bus Licence"),
    ("passport", "Passport"),
    ("blue_card", "Blue Card"),
    ("forklift_licence", "Forklift Licence"),
    ("additional", "Additional Licence"),
]

# Dict form of LICENCE_PRESETS for O(1) lookups by key
LICENCE_PRESET_LABELS = dict(LICENCE_PRESETS)


class Form(models.Model):
    """A configurable form template created by an admin or manager.

    Forms are composed of Question records and can be assigned to users or
    attached to ProjectRoles as required submission forms.
    """

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_forms')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        """Return the form title."""
        return self.title


class WorkerProfile(models.Model):
    """Extended profile data for site workers, linked one-to-one with CustomUser.

    Stores operational details that are not part of Django's built-in user model
    (DOB, job role, employer, emergency contact).
    """

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
        """Return a human-readable label showing which user this profile belongs to."""
        return f"Profile for {self.user.get_full_name() or self.user.email}"


def upload_path(instance, filename):
    """Build a storage path for a Credential image file.

    Organises uploads under credentials/<user_id>/<title><ext> so that each
    user's credential images are grouped together in storage.

    Args:
        instance (Credential): The Credential instance being saved.
        filename (str): The original uploaded filename.

    Returns:
        str: The relative storage path for the file.
    """
    ext = os.path.splitext(filename)[1]
    return f"credentials/{instance.user_id}/{instance.title}{ext}"


class Credential(models.Model):
    """A licence, certification, or ID document held by a worker.

    Credentials can be required (Site Induction, Medical, Photo ID) or optional
    (Driver Licence, additional licences). Expiry dates drive the compliance
    status and automated renewal reminder emails.
    """

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
        """Return 'TBA', 'Expired', or 'Compliant' based on today's date.

        'TBA' is returned when either the issue or expiry date is missing so the
        UI can distinguish between credentials that haven't been filled in yet
        and those that are actively tracked.
        """
        if not self.issue_date or not self.expiry_date:
            return "TBA"
        return "Expired" if self.expiry_date < timezone.localdate() else "Compliant"

    @property
    def is_additional(self):
        """Return True if this credential is not one of the known preset types.

        Additional credentials are user-defined and displayed separately from
        the fixed required/optional preset list on the profile page.
        """
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
        """Return the credential title and whether it is required or optional."""
        return f"{self.title} ({'Required' if self.required else 'Optional'})"

    
class Question(models.Model):
    """A single question within a Form, supporting many input types.

    For radio/checkbox/dropdown questions, options_text stores the choices as a
    newline-separated string. For licence_upload questions, options_text holds
    the licence preset label (e.g. "Driver Licence") used to look up the
    worker's existing credential image.
    """

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
        """Return the form title and a truncated version of the question text."""
        return f"{self.form.title} - {self.question_text[:50]}"

    @property
    def options(self):
        """Parse options_text into a list of stripped, non-empty option strings.

        Returns:
            list[str]: Individual options, or an empty list for non-choice question types.
        """
        if self.options_text:
            return [opt.strip() for opt in self.options_text.split('\n') if opt.strip()]
        return []


class FormAssignment(models.Model):
    """Records that a specific Form has been assigned to a specific user.

    Created automatically when a user is invited to a ProjectRole that has a
    required_form. The unique_together constraint prevents duplicate assignments.
    """

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
        """Return a label showing which form is assigned to which user."""
        return f"{self.form.title} → {self.user.email}"


class FormSubmission(models.Model):
    """A completed submission of a Form by a user.

    Each submission is a parent record; the individual question answers are
    stored as related Answer objects. A user may have multiple submissions for
    the same form (e.g. after a rejection and re-submit).
    """

    form = models.ForeignKey(
        Form,
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
        """Return a label showing the user, form, and submission timestamp."""
        return f"{self.user.email} - {self.form.title} - {self.submitted_at}"


class FormDraft(models.Model):
    """Persists in-progress form answers for a user/invite combination.

    Answers are stored as a JSON dict keyed by "question_<id>" so the form
    view can re-populate fields if the user navigates away and returns. Each
    (user, invite) pair has at most one draft (unique_together).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
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
    """A single question's answer within a FormSubmission.

    Text-based answers go in answer_text; file/image uploads go in answer_file.
    """

    submission = models.ForeignKey(FormSubmission, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    answer_text = models.TextField(blank=True)
    answer_file = models.ImageField(upload_to="form_answers/%Y/%m/", null=True, blank=True)

    def __str__(self):
        """Return the submitter's email and a truncated copy of the question text."""
        return f"{self.submission.user.email} - {self.question.question_text[:30]}"


class SubmissionCredentialAttachment(models.Model):
    """A snapshot copy of a worker's credential image attached to a submission.

    Stores a copy of the image at submission time so that the record remains
    intact even if the source Credential is later updated or deleted.
    source_credential is nullable because the original may be deleted.
    """

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
        """Return the submitter's email and the credential title."""
        return f"{self.submission.user.email} - {self.title}"

class Project(models.Model):
    """A mine-site project that workers are assigned to via ProjectRoles.

    Projects have a start date and an optional end date. When end_date is None
    the project is treated as indefinite and timeline progress is not shown.
    """

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
        """Return True when no end date has been set for this project."""
        return self.end_date is None

    def __str__(self):
        """Return the project title."""
        return self.title


class ProjectRole(models.Model):
    """A named role within a Project (e.g. "Operator", "Site Supervisor").

    Each role can optionally require a specific Form to be completed before a
    worker's invite is reviewed and approved. Role titles must be unique per
    project (enforced by unique_together).
    """

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
        """Return a label combining the project title and role title."""
        return f"{self.project.title} - {self.title}"


class ProjectInvite(models.Model):
    """Represents a worker's invitation to fill a specific ProjectRole.

    Tracks two separate state machines:
      - status: whether the worker has submitted the required form
        (pending → viewed → completed)
      - review_status: whether an admin has reviewed the submission
        (pending_review → approved | rejected)

    The unique_together on (project_role, user) means a worker can only hold
    one invite per role at a time.
    """

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
        """Return a description of who was invited, to which project and role."""
        return f"{self.user.email} invited to {self.project.title} as {self.project_role.title}"


def approval_document_upload_path(instance, filename):
    """Build a storage path for ApprovalDocument files under the project's folder.

    Args:
        instance (ApprovalDocument): The document instance being saved.
        filename (str): The original uploaded filename.

    Returns:
        str: The relative storage path for the file.
    """
    return f"approval_documents/{instance.project_id}/{filename}"


class ApprovalDocument(models.Model):
    """A PDF document attached to a project, role, or individual user for approval purposes.

    Scope controls which invite records the document is relevant to:
      - "project": shown to all members of the project
      - "role":    shown only to members with a specific role
      - "user":    shown only to a specific worker
    """

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
        """Return the project title, document title, and scope."""
        return f"{self.project.title} - {self.title} ({self.scope})"


class OnboardingInvite(models.Model):
    """Tracks the onboarding lifecycle for a new worker invited via email.

    Status progression:
      sent → account_created (or default_form_pending if a default form is required)
           → completed
    The token is included in the setup URL emailed to the worker.
    """

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
        """Return the invitee's email and current status."""
        return f"{self.email} - {self.status}"


class CredentialNotification(models.Model):
    """Records that a reminder notification has been sent for a credential at a given band.

    The unique_together constraint prevents duplicate emails for the same
    credential/band combination. The send_licence_expiry_reminders management
    command checks this table before sending to avoid re-sending.
    """

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
        """Return the credential and the reminder band that was notified."""
        return f"{self.credential} - {self.reminder_band}"


class LicenceRenewalRequest(models.Model):
    """A tokenised renewal request sent to a worker when their driver's licence is expiring.

    The token is embedded in the renewal URL so the worker can update their
    licence without logging in. is_used is set to True once the worker confirms,
    preventing the link from being reused.
    """

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
        """Return the user email, credential title, and reminder band."""
        return f"{self.user.email} - {self.credential.title} - {self.reminder_band}"
    
