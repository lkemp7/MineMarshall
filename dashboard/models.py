from django.db import models
from django.contrib.auth.models import AbstractUser

class Contractor(models.Model):
    firstName = models.CharField(max_length=255)
    lastName = models.CharField(max_length=255)
    email = models.CharField(max_length=255)
    phoneNumber = models.CharField(max_length=25)
    
    def __str__(self):
        return f"{self.firstName} {self.lastName}, {self.email}"