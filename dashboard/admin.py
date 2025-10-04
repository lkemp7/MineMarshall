from django.contrib import admin
from accounts.models import CustomUser
from .models import Form, Question

admin.site.register(CustomUser)

class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0

@admin.register(Form)
class FormAdmin(admin.ModelAdmin):
    list_display = ("title", "created_by", "created_at")
    inlines = [QuestionInline]
