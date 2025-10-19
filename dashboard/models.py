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