from django.contrib import admin
from accounts.models import CustomUser
from .models import Form, Question
from django.contrib import admin
from .models import Project, ProjectRole, ProjectInvite, ApprovalDocument
from .models import Credential, Question, Answer, SubmissionCredentialAttachment
from .models import WorkerProfile, Credential, FormSubmission, Answer, OnboardingInvite

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
    model = Question
    extra = 0

@admin.register(Form)
class FormAdmin(admin.ModelAdmin):
    list_display = ("title", "created_by", "created_at")
    inlines = [QuestionInline]

admin.site.register(OnboardingInvite)
