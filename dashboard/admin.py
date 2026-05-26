from django.contrib import admin
from accounts.models import CustomUser
from .models import Form, Question
from django.contrib import admin
from .models import Project, ProjectRole, ProjectInvite, ApprovalDocument
from .models import Credential, Question, Answer, SubmissionCredentialAttachment
from .models import WorkerProfile, Credential, FormSubmission, Answer, OnboardingInvite

# Flat registrations expose all models in the Django admin with default list views.
admin.site.register(Credential)
admin.site.register(Question)
admin.site.register(Answer)
admin.site.register(SubmissionCredentialAttachment)
admin.site.register(Project)
admin.site.register(ProjectRole)
admin.site.register(ProjectInvite)
admin.site.register(ApprovalDocument)

admin.site.register(CustomUser)


class QuestionInline(admin.TabularInline):
    """Inline editor for Questions nested inside the Form admin change page."""

    model = Question
    extra = 0


@admin.register(Form)
class FormAdmin(admin.ModelAdmin):
    """Custom Form admin: shows title, creator, and creation date in the list view,
    and embeds a QuestionInline so questions can be edited on the same page."""

    list_display = ("title", "created_by", "created_at")
    inlines = [QuestionInline]


admin.site.register(OnboardingInvite)
