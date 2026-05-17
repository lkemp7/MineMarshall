from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from accounts.models import CustomUser
from dashboard.models import Credential, OnboardingInvite, Project, ProjectRole, ProjectInvite, Form, FormAssignment, Question
from dashboard.views import _user_has_compliance_issue, _project_member_status
from django.db import IntegrityError
from datetime import date, timedelta
from unittest.mock import patch


class CredentialStatusTest(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="user@test.com",
            password="password",
            role="user"
        )

    def test_compliant_when_expiry_in_future(self):
        cred = Credential.objects.create(
            user=self.user,
            title="Driver Licence",
            issue_date=timezone.now().date() - timezone.timedelta(days=300),
            expiry_date=timezone.now().date() + timezone.timedelta(days=30)
        )
        self.assertEqual(cred.status, "Compliant")

    def test_expired_when_expiry_in_past(self):
        cred = Credential.objects.create(
            user=self.user,
            title="Driver Licence",
            issue_date=timezone.now().date() - timezone.timedelta(days=300),
            expiry_date=timezone.now().date() - timezone.timedelta(days=30)
        )
        self.assertEqual(cred.status, "Expired")

    def test_tba_if_dates_missing(self):
        cred = Credential.objects.create(
            user=self.user,
            title="Driver Licence"
        )
        self.assertEqual(cred.status, "TBA")

    def test_edge_expiry_today(self):
        cred = Credential.objects.create(
            user=self.user,
            title="Driver Licence",
            issue_date=timezone.now().date() - timezone.timedelta(days=300),
            expiry_date=timezone.now().date()
        )
        self.assertEqual(cred.status, "Compliant")
        
    def test_exppired_credential_triggers_compliance_issue(self):
        Credential.objects.create(
        user=self.user,
        title="Drivers Licence",
        expiry_date=date.today() - timedelta(days=1)
        )
        issue, expired = _user_has_compliance_issue(self.user)
        self.assertTrue(issue)
        self.assertEqual(len(expired), 1)


class EmailTokenTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="admin",
            email="admin@test.com",
            password="pass",
            role="admin"
        )
        self.user = CustomUser.objects.create_user(
            username="user",
            email="user@test.com",
            password="pass",
            role="user"
        )

    def test_email_token_unique(self):
        OnboardingInvite.objects.create(
            user=self.user,
            email="user@test.com",
            first_name="test",
            last_name="test",
            token="token123"
        )
        with self.assertRaises(IntegrityError):
            OnboardingInvite.objects.create(
                user=self.admin,
                email="admin@test.com",
                first_name="test",
                last_name="test",
                token="token123"
            )


class ProjectModelTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="testuser",
            email="user@test.com",
            password="password",
            role="user"
        )

    def test_is_indefinite_when_no_end_date(self):
        project = Project.objects.create(
            title="Ongoing Project",
            start_date=date.today(),
            created_by=self.admin,
            end_date=None
        )
        self.assertTrue(project.is_indefinite)

    def test_not_indefinite_when_end_date_set(self):
        project = Project.objects.create(
            title="Ongoing Project",
            start_date=date.today(),
            created_by=self.admin,
            end_date=date.today() + timedelta(days=90)
        )
        self.assertFalse(project.is_indefinite)


class ProjectConstraintsTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="testadmin",
            email="admin@test.com",
            password="password",
            role="admin"
        )
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="user@test.com",
            password="password",
            role="user"
        )
        self.project = Project.objects.create(
            title="Test Project",
            start_date=date.today(),
            created_by=self.admin
        )
        self.role = ProjectRole.objects.create(
            project=self.project,
            title="SWE"
        )

    def test_duplicate_role_title_in_same_project_raises_error(self):
        with self.assertRaises(IntegrityError):
            ProjectRole.objects.create(project=self.project, title="SWE")

    def test_duplicate_project_invite_raises_error(self):
        ProjectInvite.objects.create(
            project=self.project, project_role=self.role,
            user=self.user, invited_by=self.admin
        )
        with self.assertRaises(IntegrityError):
            ProjectInvite.objects.create(
                project=self.project,
                project_role=self.role,
                user=self.user,
                invited_by=self.admin
            )
            
class FormAssignmentTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="testadmin",
            email="admin@test.com",
            password="password",
            role="admin"
        )
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="user@test.com",
            password="password",
            role="user"
        )
        self.form = Form.objects.create(
            title="Test Form",
            created_by=self.admin
        )
        
    def test_new_assignment_is_incomplete(self):
        assignment = FormAssignment.objects.create(
            form=self.form,
            user=self.user,
            assigned_by=self.admin
        )
        self.assertFalse(assignment.completed)
        self.assertIsNone(assignment.completed_at)
        
    def test_form_only_assigned_once_per_user(self):
        FormAssignment.objects.create(
            form=self.form,
            user=self.user,
            assigned_by=self.admin
        )
        with self.assertRaises(IntegrityError):
            FormAssignment.objects.create(
                form=self.form,
                user=self.user,
                assigned_by=self.admin
        )
            
class CreateFormTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="testadmin",
            email="admin@test.com",
            password="password",
            role="admin"
        )
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="user@test.com",
            password="password",
            role="user"
        )
    
    def test_unauthenticated_redirect(self):
        response = self.client.get(reverse('create_form'))
        self.assertEqual(response.status_code, 302)
        
    def test_user_forbidden(self):
        self.client.login(username="user@test.com",
                          password="password")
        response = self.client.post(reverse('create_form'),
                                   {"title": "Form123"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Form.objects.filter(title="Form123").exists())
        
    def test_admin_can_create_forms(self):
        self.client.login(username="admin@test.com",
                          password="password")
        response = self.client.post(reverse('create_form'), {
            'title': 'Test Form',
            'description': 'Test Description',
            'questions[abc1][text]': 'What is your name?',
            'questions[abc1][type]': 'text',
            'questions[abc1][required]': 'on',
        })
        self.assertTrue(Form.objects.filter(title='Test Form').exists())
        self.assertTrue(Question.objects.filter(question_text='What is your name?').exists())
        self.assertEqual(response.get('HX-Redirect'), '/dashboard/forms/mine/')
        
    def test_questions_saved_in_order(self):
        self.client.login(username="admin@test.com", 
                          password="password")
        self.client.post(reverse('create_form'), {
            'title': 'Multi Question Form',
            'questions[id1][text]': 'First Question',
            'questions[id1][type]': 'text',
            'questions[id1][required]': 'on',
            'questions[id2][text]': 'Second Question',
            'questions[id2][type]': 'textarea',
        })
        
        form = Form.objects.get(title='Multi Question Form')
        questions = list(form.questions.order_by('order'))
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0].question_text, 'First Question')
        self.assertEqual(questions[0].order, 1)
        self.assertEqual(questions[1].question_text, 'Second Question')
        self.assertEqual(questions[1].order, 2)
        
class UpdateFormTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="testadmin",
            email="admin@test.com",
            password="password",
            role="admin"
        )
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="user@test.com",
            password="password",
            role="user"
        )
        self.form = Form.objects.create(
            title="Test Form",
            created_by=self.admin
        )
        
        Question.objects.create(
            form=self.form, 
            question_text="Old Q1", 
            question_type="text", 
            order=1
        )
        Question.objects.create(
            form=self.form, 
            question_text="Old Q2", 
            question_type="text", 
            order=2
        )
        Question.objects.create(
            form=self.form, 
            question_text="Old Q3", 
            question_type="text", 
            order=3
        )
    
    def test_saves_all_questions(self):
        self.client.login(username="admin@test.com",
                          password="password")
        self.client.post(reverse('update_form',
                                 args=[self.form.pk]), {
                                     'title': 'Updated Title',
                                     'description': '',
                                     'questions[id1][text]': 'New Question 1',
                                     'questions[id1][type]': 'text',
                                     'questions[id1][required]': 'on',
                                     'questions[id2][text]': 'New Question 2',
                                     'questions[id2][type]': 'text',
                                 })
        self.assertEqual(self.form.questions.count(), 2)
        
    def test_new_questions_replace_old(self):
        self.client.login(username="admin@test.com",
                          password="password")
        self.client.post(reverse('update_form', args=[self.form.pk]), {
            'title': 'Updated Title',
            'questions[id1][text]': 'Only Question',
            'questions[id1][type]': 'text',
            'questions[id1][required]': 'on',
        })
        self.assertEqual(self.form.questions.count(), 1)
        
    def test_returns_hx_redirect_header(self):
        self.client.login(username="admin@test.com",
                          password="password")
        response = self.client.post(reverse('update_form', args=[self.form.pk]), {
            'title': 'Updated Title',
            'questions[id1][text]': 'A Question',
            'questions[id1][type]': 'text',
        })
        self.assertEqual(response.get('HX-Redirect'), '/dashboard/forms/mine/')
        
    def test_get_returns_405(self):
        self.client.login(username="admin@test.com",
                          password="password")
        response = self.client.get(reverse('update_form', args=[self.form.pk]))
        self.assertEqual(response.status_code, 405)
        
    def test_user_forbidden(self):
        self.client.login(username="user@test.com",
                          password="password")
        response = self.client.post(reverse('update_form', args=[self.form.pk]),{
            'title': 'Forbidden form',
        })
        self.assertEqual(response.status_code, 403)
        self.form.refresh_from_db()
        self.assertEqual(self.form.title, 'Test Form')
        
class DeleteFormTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="testadmin",
            email="admin@test.com",
            password="password",
            role="admin"
        )
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="user@test.com",
            password="password",
            role="user"
        )
        self.form = Form.objects.create(
            title="Test Form",
            created_by=self.admin
        )
        
    def test_admin_delete_form(self):
        self.client.login(username="admin@test.com",
                            password="password")
        self.client.post(reverse('delete_form', args=[self.form.pk]))
        self.assertFalse(Form.objects.filter(pk=self.form.pk).exists())
        
    def test_user_cannot_delete_form(self):
        self.client.login(username="user@test.com",
                          password="password")
        self.client.post(reverse('delete_form', args=[self.form.pk]))
        self.assertTrue(Form.objects.filter(pk=self.form.pk).exists())
        
class ProjectsTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="testadmin",
            email="admin@test.com",
            password="password",
            role="admin"
        )
    
    def admin_can_create_project(self):
        self.client.login(username="admin@test.com",
                            password="password")
        response = self.client.post(reverse('projects'), {
            'title': 'New Project',
            'description': 'This is a new project',
            'start_date': '2026-01-01',
        })
        self.assertTrue(Project.objects.filter(title='New Project').exists())
        project = Project.objects.get(title='New Project')
        self.assertRedirects(response, reverse('project_detail', args=[project.pk]))
        
    def test_missing_title_rejected(self):
        self.client.login(username="admin@test.com",
                            password="password")
        
        self.client.post(reverse('projects'), {
            'title': '',
            'start_date': '2026-01-01',
        })
        
        self.assertFalse(Project.objects.exists())
        
    def test_end_date_before_start_date_rejected(self):
        self.client.login(username="admin@test.com", 
                          password="password")
        self.client.post(reverse('projects'), {
            'title': '123',
            'start_date': '2026-06-01',
            'end_date': '2026-01-01',
        })
        self.assertFalse(Project.objects.filter(title='123').exists())
        
class TestDeleteProjects(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="testadmin",
            email="admin@test.com",
            password="password",
            role="admin"
        )
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="user@test.com",
            password="password",
            role="user"
        )
        self.project = Project.objects.create(
            title="Test",
            start_date=date.today(),
            created_by=self.admin
        )
    
    def admin_can_delete_project(self):
        self.client.login(username="admin@test.com", 
                          password="password")
        response = self.client.post(reverse('delete_project', args=[self.project.pk]))
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())
        self.assertRedirects(response, reverse('projects'))
        
    def test_user_cannot_delete_project(self):
        self.client.login(username="user@test.com", 
                          password="password")
        response = self.client.post(reverse('delete_project', args=[self.project.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())
        
class DeleteUserTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="testadmin",
            email="admin@test.com",
            password="password",
            role="admin"
        )
        self.manager = CustomUser.objects.create_user(
            username="testmanager",
            email="manager@test.com",
            password="password",
            role="manager"
        )
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="user@test.com",
            password="password",
            role="user"
        )
        self.user2 = CustomUser.objects.create_user(
            username="testuser2",
            email="user2@test.com",
            password="password",
            role="user"
        )
        
    def test_admin_deletes_user(self):
        self.client.login(username="admin@test.com", 
                        password="password")
        self.client.post(reverse('delete_user', args=[self.user.pk]))
        self.assertFalse(CustomUser.objects.filter(pk=self.user.pk).exists())

    def test_manager_deletes_user(self):
        self.client.login(username="manager@test.com", 
                        password="password")
        self.client.post(reverse('delete_user', args=[self.user.pk]))
        self.assertFalse(CustomUser.objects.filter(pk=self.user.pk).exists())
        
    def test_cannot_delete_self(self):
        self.client.login(username="admin@test.com", 
                        password="password")
        self.client.post(reverse('delete_user', args=[self.admin.pk]))
        self.assertTrue(CustomUser.objects.filter(pk=self.admin.pk).exists())
        
    def test_manager_cannot_delete_admin(self):
        self.client.login(username="manager@test.com", 
                        password="password")
        self.client.post(reverse('delete_user', args=[self.admin.pk]))
        self.assertTrue(CustomUser.objects.filter(pk=self.admin.pk).exists())

    def test_user_cannot_delete_anyone(self):
        self.client.login(username="user@test.com", 
                        password="password")
        self.client.post(reverse('delete_user', args=[self.admin.pk]))
        self.client.post(reverse('delete_user', args=[self.manager.pk]))
        self.client.post(reverse('delete_user', args=[self.user2.pk]))
        self.assertTrue(CustomUser.objects.filter(pk=self.admin.pk).exists())
        self.assertTrue(CustomUser.objects.filter(pk=self.manager.pk).exists())
        self.assertTrue(CustomUser.objects.filter(pk=self.user2.pk).exists())

class InductionTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="testadmin",
            email="admin@test.com",
            password="password",
            role="admin"
        )
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="user@test.com",
            password="password",
            role="user"
        )
        
    def test_admin_creates_new_user(self):
        self.client.login(username="admin@test.com", 
                        password="password")
        self.client.post(reverse('start_induction'), {
            'first_name': 'abc',
            'last_name': 'def',
            'email': 'abcdef@test.com',
        })
        
        user = CustomUser.objects.get(email="abcdef@test.com")
        self.assertFalse(user.is_active) # user inactive until onbarding is complete
        self.assertTrue(OnboardingInvite.objects.filter(email="abcdef@test.com").exists())
        
        
    def test_setup_email_is_sent(self):
        self.client.login(username="admin@test.com", 
                        password="password")
        self.client.post(reverse('start_induction'), {
            'first_name': 'abc',
            'last_name': 'def',
            'email': 'abcdef@test.com',
        })
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('abcdef@test.com', mail.outbox[0].to)
         
    def test_duplicate_email_rejected(self):
        self.client.login(username="admin@test.com", 
                        password="password")
        self.client.post(reverse('start_induction'), {
            'first_name': 'abc',
            'last_name': 'def',
            'email': 'abcdef@test.com',
        })
        self.assertEqual(CustomUser.objects.filter(email='user@test.com').count(), 1)
        
    def test_user_cannot_start_induction(self):
        self.client.login(username="user@test.com", 
                        password="password")
        self.client.post(reverse('start_induction'), {
            'first_name': 'abc',
            'last_name': 'def',
            'email': 'abcdef@test.com',
        })
        
        self.assertFalse(CustomUser.objects.filter(email="abcdef@test.com").exists())
        
class LicenceScanTest(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="user@test.com",
            password="password",
            role="user"
        )
        self.invite = OnboardingInvite.objects.create(
            user=self.user,
            email="user@test.com",
            first_name="abc",
            last_name="def",
            token="token123"
        )
        self.client.login(username="user@test.com", 
                          password="password")
        
    @patch('accounts.views.extract_licence_fields')
    def test_successful_scan_creates_credential(self, mock_ocr):
        mock_ocr.return_value = {
            "title": "Driver Licence",
            "first_name": "abc", 
            "last_name": "def",
            "dob": "1901-01-01", 
            "licence_number": "123456789",
            "expiry": "2026-12-31"
        }
        image = SimpleUploadedFile("licence.jpg", b"bytes", content_type="image/jpeg")
        response = self.client.post(reverse('licence_scan', kwargs={'token': "token123"}), {'licence_image': image})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Credential.objects.filter(user=self.user).exists())
        
    @patch("accounts.views.extract_licence_fields")
    def test_unreadable_image_doesnt_save_credential(self, mock_ocr):
        mock_ocr.return_value = {
            "title": None,
            "first_name": None, 
            "last_name": None,
            "dob": None, 
            "licence_number": None,
            "expiry": None
        }
        image = SimpleUploadedFile("licence.jpg", b"bytes", content_type="image/jpeg")
        response = self.client.post(reverse('licence_scan', kwargs={'token': "token123"}), {'licence_image': image})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Credential.objects.filter(user=self.user).exists())
        
class MetricsTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="testadmin",
            email="admin@test.com",
            password="password",
            role="admin"
        )
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="user@test.com",
            password="password",
            role="user"
        )
        self.invite = OnboardingInvite.objects.create(
            user=self.user,
            email="user@test.com",
            first_name="abc",
            last_name="def",
            token="token123"
        )
        self.project = Project.objects.create(
            title="Test Project",
            start_date=date.today(),
            created_by=self.admin
        )
        self.role = ProjectRole.objects.create(
            project=self.project,
            title="Test Role"
        )
    
    def test_admin_can_access_metrics(self):
        self.client.login(username="admin@test.com", 
                          password="password")
        response = self.client.get(reverse('metrics'))
        self.assertEqual(response.status_code, 200)
        
class UserProfileTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="testadmin",
            email="admin@test.com",
            password="password",
            role="admin"
        )
        self.admin2 = CustomUser.objects.create_user(
            username="testadmin2",
            email="admin2@test.com",
            password="password",
            role="admin"
        )
        self.manager = CustomUser.objects.create_user(
            username="testmanager",
            email="manager@test.com",
            password="password",
            role="manager"
        )
        self.manager2 = CustomUser.objects.create_user(
            username="testmanager2",
            email="manager2@test.com",
            password="password",
            role="manager"
        )
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="user@test.com",
            password="password",
            role="user"
        )
        self.user2 = CustomUser.objects.create_user(
            username="testuser2",
            email="user2@test.com",
            password="password",
            role="user"
        )
        
        self.BASE_POST = {
            'first_name': '',
            'last_name': '',
            'email': '',
            'phone_number': '',
            'worker_role': '',
            'project': '',
            'employer': '',
            'emergency_contact_name': '',
            'emergency_contact_mobile': '',
        }
        
    def test_admin_can_view_any_profile(self):
        self.client.login(username="admin@test.com",
                          password="password")
        response = self.client.get(reverse('user_profile', kwargs={'user_id': self.admin2.pk}))
        response2 = self.client.get(reverse('user_profile', kwargs={'user_id': self.manager.pk}))
        response3 = self.client.get(reverse('user_profile', kwargs={'user_id': self.user.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response3.status_code, 200)
        
    def test_manager_cannot_view_admin(self):
        self.client.login(username="manager@test.com",
                          password="password")
        response = self.client.get(reverse('user_profile', kwargs={'user_id': self.admin.pk}))
        self.assertEqual(response.status_code, 302)
    
    def test_manager_can_view_user_profile(self):
        self.client.login(username="manager@test.com",
                          password="password")
        response = self.client.get(reverse('user_profile', kwargs={'user_id': self.user.pk}))
        self.assertEqual(response.status_code, 200)
        
    def test_user_can_only_view_own_profile(self):
        self.client.login(username="user@test.com",
                          password="password")
        response = self.client.get(reverse('user_profile', kwargs={'user_id': self.admin.pk}))
        response2 = self.client.get(reverse('user_profile', kwargs={'user_id': self.manager.pk}))
        response3 = self.client.get(reverse('user_profile', kwargs={'user_id': self.user2.pk}))
        response4 = self.client.get(reverse('user_profile', kwargs={'user_id': self.user.pk}))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response2.status_code, 403)
        self.assertEqual(response3.status_code, 403)
        self.assertEqual(response4.status_code, 200)
        
        
    def test_admin_can_edit_any_profile(self):
        self.client.login(username="admin@test.com",
                          password="password")
        response = self.client.post(reverse('edit_user_profile', kwargs={'pk': self.admin2.pk}), data={**self.BASE_POST, 'first_name': 'updated name', 'email': 'admin2@test.com'})
        response2 = self.client.post(reverse('edit_user_profile', kwargs={'pk': self.manager.pk}), data={**self.BASE_POST, 'first_name': 'updated name', 'email': 'manager@test.com'})
        response3 = self.client.post(reverse('edit_user_profile', kwargs={'pk': self.user.pk}), data={**self.BASE_POST, 'first_name': 'updated name', 'email': 'user@test.com'})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response2.status_code, 204)
        self.assertEqual(response3.status_code, 204)
        self.admin2.refresh_from_db()
        self.manager.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.admin2.first_name, 'updated name')
        self.assertEqual(self.manager.first_name, 'updated name')
        self.assertEqual(self.user.first_name, 'updated name')
    
    def test_manager_cannot_edit_manager_or_admin_profiles(self):
        self.client.login(username="manager@test.com",
                          password="password")
        response = self.client.post(reverse('edit_user_profile', kwargs={'pk': self.manager2.pk}), data={**self.BASE_POST, 'first_name': 'updated name', 'email': 'admin@test.com'})
        response2 = self.client.post(reverse('edit_user_profile', kwargs={'pk': self.admin.pk}), data={**self.BASE_POST, 'first_name': 'updated name', 'email': 'manager2@test.com'})
        self.assertNotEqual(response.status_code, 204)
        self.assertNotEqual(response2.status_code, 204)
        self.admin.refresh_from_db()
        self.manager2.refresh_from_db()
        self.assertNotEqual(self.admin.first_name, 'updated name')
        self.assertNotEqual(self.manager2.first_name, 'updated name')
        
    def test_manager_can_edit_user_profile(self):
        self.client.login(username="manager@test.com",
                          password="password")

        response = self.client.post(reverse('edit_user_profile', kwargs={'pk': self.user.pk}), data={**self.BASE_POST, 'first_name': 'updated name', 'email': 'user@test.com'})
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'updated name')
        
    def test_user_can_edit_own_profile(self):
        self.client.login(username="user@test.com",
                          password="password")
        
        response = self.client.post(reverse('edit_user_profile', kwargs={'pk': self.user.pk}), data={**self.BASE_POST, 'first_name': 'updated name', 'email': 'user@test.com'})
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'updated name')