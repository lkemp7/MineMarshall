from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from accounts.models import CustomUser
from .models import Form, Question
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404

@login_required
def dashboard(request):
    users = CustomUser.objects.all()
    context = {'users': users}
    return render(request, 'dashboard.html', context)


@login_required
def create_form(request):
    # Only allow this exact user to create forms for now
    if request.user.email.lower() != "admin@minemarshall.com":
        return HttpResponseForbidden("You are not allowed to create forms.")

    if request.method == "POST":
        title = request.POST.get("title", "").strip() or "Untitled Form"
        try:
            num_questions = int(request.POST.get("num_questions", "0"))
        except ValueError:
            num_questions = 0

        # Create the form
        form_obj = Form.objects.create(title=title, created_by=request.user)

        # Create questions
        for i in range(1, num_questions + 1):
            q_text = (request.POST.get(f"question_{i}", "") or "").strip()
            if q_text:
                Question.objects.create(form=form_obj, text=q_text, order=i)

        return redirect("my_forms")

    return render(request, "create_form.html", {})


@login_required
def my_forms(request):
    # Only show forms created by the logged-in user
    forms = Form.objects.filter(created_by=request.user).order_by("-created_at")
    return render(request, "my_forms.html", {"forms": forms})


@login_required
def view_form(request, pk):
    form_obj = get_object_or_404(Form, pk=pk, created_by=request.user)
    return render(request, "form_detail.html", {"form": form_obj})


@login_required
def personnel(request):
    users = CustomUser.objects.all().order_by("first_name", "last_name")
    return render(request, 'personnel.html', {"users": users})
