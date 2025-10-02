# accounts/forms.py
from django import forms
from .models import CustomUser
from django.core.exceptions import ValidationError

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        # fields the user is allowed to edit in their profile
        fields = ['first_name', 'last_name', 'email', 'phone_number']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # add nice Tailwind/DaisyUI classes to all fields (optional)
        for name, field in self.fields.items():
            field.widget.attrs.update({
                'class': 'input input-bordered w-full',
                'placeholder': field.label
            })

    def clean_email(self):
        # ensure email is unique, but allow current user's own email
        email = self.cleaned_data.get('email')
        qs = CustomUser.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("A user with that email already exists.")
        return email
