from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=25)
    
    ROLE_CHOICES = [
        ("admin", "Full Administrator"),
        ("manager", "Manager"),
        ("user", "User")
    ]
    
    role = models.CharField(max_length = 25, choices = ROLE_CHOICES, default = "user")
    
    def save(self, *args, **kwargs):
        # Ensure username is always the email
        if self.email:
            self.username = self.email
        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"{self.first_name} {self.last_name}, {self.email}"
    
    @property
    def is_admin(self):
        return self.role == "admin"