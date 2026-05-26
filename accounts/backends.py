from django.contrib.auth.backends import ModelBackend
from accounts.models import CustomUser


class CaseInsensitiveBackend(ModelBackend):
    """Authentication backend that matches usernames case-insensitively.

    Registered in settings.AUTHENTICATION_BACKENDS so that users can log in
    with any capitalisation of their email address.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        """Look up the user by email (case-insensitive) and verify password.

        Args:
            request: The current HttpRequest.
            username: The email/username submitted in the login form.
            password: The raw password submitted in the login form.
            **kwargs: Unused extra keyword arguments forwarded by Django.

        Returns:
            The authenticated CustomUser instance, or None if authentication fails.
        """
        try:
            user = CustomUser.objects.get(username__iexact=username)
        except CustomUser.DoesNotExist:
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user