from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

# Unregister the default CustomUser registration made in dashboard/admin.py,
# then re-register with the richer CustomUserAdmin below.
admin.site.unregister(CustomUser)


class CustomUserAdmin(UserAdmin):
    """Admin configuration for CustomUser.

    Replaces Django's default UserAdmin to use email as the identifier,
    expose the phone_number and role fields, and hide the unused username field.
    """

    ordering = ('email',)
    list_display = ('email', 'first_name', 'last_name', 'phone_number', 'role')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'phone_number')}),
        ('Permissions', {'fields': ['role']}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'phone_number', 'role', 'password1', 'password2'),
        }),
    )


admin.site.register(CustomUser, CustomUserAdmin)
