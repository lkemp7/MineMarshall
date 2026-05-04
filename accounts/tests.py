from django.test import TestCase
from django.db import IntegrityError
from accounts.models import CustomUser

class CustomUserModelTest(TestCase):
    def test_username_set_to_email(self):
        user = CustomUser.objects.create_user(
            username="test",
            email="test@test.com",
            password="password",
            role="user"
        )
        self.assertEqual(user.username, "test@test.com")
        
    def test_admin_true_for_admin(self):
        user = CustomUser.objects.create_user(
            username="test",
            email="test@test.com",
            password="password",
            role="admin"
        )
        self.assertTrue(user.is_admin)
        
    def test_admin_false_for_manager(self):
        user = CustomUser.objects.create_user(
            username="test",
            email="test@test.com",
            password="password",
            role="manager"
        )
        self.assertFalse(user.is_admin)
        
    def test_admin_false_for_user(self):
        user = CustomUser.objects.create_user(
            username="test",
            email="test@test.com",
            password="password",
            role="user"
        )
        self.assertFalse(user.is_admin)
        
    def test_duplicate_email_not_allowed(self):
        user1 = CustomUser.objects.create_user(
            username="user1",
            email="email@email.com",
            password="password",
            role="user"
        )
        with self.assertRaises(IntegrityError):
            user2 = CustomUser.objects.create_user(
            username="user2",
            email="email@email.com",
            password="password",
            role="user"
            )