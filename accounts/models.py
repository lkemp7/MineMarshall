from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings

class CustomUser(AbstractUser):
    """Extended user model that uses email as the primary identifier.

    Adds phone number, profile picture, and a three-tier role system
    (admin, manager, user) on top of Django's AbstractUser.
    """

    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=25)
    profile_picture = models.ImageField(
        upload_to="profile_pictures/",
        blank=True,
        null=True
    )
    ROLE_CHOICES = [
        ("admin", "Full Administrator"),
        ("manager", "Manager"),
        ("user", "User")
    ]

    role = models.CharField(max_length=25, choices=ROLE_CHOICES, default="user")

    def save(self, *args, **kwargs):
        """Keep username in sync with email and promote superusers to admin role.

        Django's auth system still uses the username field internally, so we
        mirror email → username on every save to avoid login mismatches.
        """
        # Ensure username is always the email
        if self.email:
            self.username = self.email
        if self.is_superuser:
            self.role = "admin"
        super().save(*args, **kwargs)

    def __str__(self):
        """Return a human-readable representation of the user."""
        return f"{self.first_name} {self.last_name}, {self.email}"

    @property
    def is_admin(self):
        """Return True if the user holds the admin role or is a Django superuser."""
        return self.role == "admin" or self.is_superuser

