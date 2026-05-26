# accounts/forms.py
from django import forms
from .models import CustomUser
from django.core.exceptions import ValidationError


class UserProfileForm(forms.ModelForm):
    """ModelForm that lets a user edit their own basic profile information.

    Only exposes the fields that are safe for the user to change themselves.
    Tailwind/DaisyUI CSS classes are applied to every widget in __init__.
    """

    class Meta:
        model = CustomUser
        # Fields the user is allowed to edit in their profile
        fields = ['first_name', 'last_name', 'email', 'phone_number']

    def __init__(self, *args, **kwargs):
        """Apply DaisyUI input styling to all form fields."""
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.update({
                'class': 'input input-bordered w-full',
                'placeholder': field.label
            })

    def clean_email(self):
        """Validate that the email is unique, ignoring the current user's own record.

        Returns:
            str: The normalised email address.

        Raises:
            ValidationError: If another user already holds this email.
        """
        email = self.cleaned_data.get('email')
        qs = CustomUser.objects.filter(email__iexact=email)
        if self.instance.pk:
            # Exclude the current user so they can keep their existing email
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("A user with that email already exists.")
        return email
