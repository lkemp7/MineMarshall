from django.contrib.auth.decorators import login_required
from accounts.models import CustomUser
from .models import Form, Question, FormAssignment, FormSubmission, Answer
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.db import models
from django.contrib import messages
from django.db import transaction


@login_required
def dashboard(request):
    users = CustomUser.objects.all()
    context = {'users': users}
    return render(request, 'dashboard.html', context)


@login_required
def create_form(request):
    if getattr(request.user, "role", None) != "admin":
        return HttpResponseForbidden("Admins only")

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        q_texts = request.POST.getlist("q_text[]")
        q_types = request.POST.getlist("q_type[]")
        q_opts  = request.POST.getlist("q_opts[]")

        if not title:
            messages.error(request, "Please provide a form title.")
            return render(request, "create_form.html", {"prefill_title": title})

        if not q_texts:
            messages.error(request, "Please add at least one question.")
            return render(request, "create_form.html", {"prefill_title": title})

        # Make lengths consistent (pad q_types/q_opts if needed)
        n = len(q_texts)
        if len(q_types) < n:
            q_types += ["text"] * (n - len(q_types))
        if len(q_opts) < n:
            q_opts += [""] * (n - len(q_opts))

        # Validate choice questions have options
        for i in range(n):
            qtype = (q_types[i] or "text").strip()
            opts  = (q_opts[i] or "").strip()
            if qtype in ("mcq", "dropdown") and not opts:
                messages.error(request, f"Question {i+1} is {qtype} and needs options (one per line).")
                return render(request, "create_form.html", {"prefill_title": title})

        with transaction.atomic():
            form = Form.objects.create(title=title, created_by=request.user)
            for i in range(n):
                text = (q_texts[i] or "").strip()
                if not text:
                    continue
                qtype = (q_types[i] or "text").strip()
                opts  = (q_opts[i] or "").strip()
                Question.objects.create(
                    form=form,
                    text=text,
                    question_type=qtype if qtype in ("text", "mcq", "dropdown") else "text",
                    options_text=opts if qtype in ("mcq", "dropdown") else "",
                    order=i,
                )

        messages.success(request, "Form created.")
        return redirect("view_form", pk=form.pk)

    return render(request, "create_form.html")

@login_required
def delete_form(request, pk):
    form_obj = get_object_or_404(Form, pk=pk)

    # permission: admin OR creator can delete
    is_admin = getattr(request.user, "role", None) == "admin"
    is_creator = getattr(form_obj, "created_by_id", None) == request.user.id
    if not (is_admin or is_creator):
        return HttpResponseForbidden("You don't have permission to delete this form.")

    # Pre-compute impact counts for the confirm screen
    questions_count = form_obj.questions.count()
    assignments_count = form_obj.assignments.count()
    submissions_count = form_obj.submissions.count()

    if request.method == "POST":
        title = form_obj.title  # keep for message
        form_obj.delete()  # cascades to questions/assignments/submissions/answers via FK on_delete=CASCADE
        messages.success(request, f'Form "{title}" was deleted.')
        return redirect("my_forms")  # or "dashboard" if you prefer

    return render(request, "confirm_delete_form.html", {
        "form_obj": form_obj,
        "questions_count": questions_count,
        "assignments_count": assignments_count,
        "submissions_count": submissions_count,
    })


@login_required
def my_forms(request):
    # Forms assigned to me
    assigned_form_ids = FormAssignment.objects.filter(user=request.user)\
        .values_list("form_id", flat=True)

    forms = Form.objects.filter(pk__in=assigned_form_ids).order_by("-created_at").distinct()

    if request.user.role == "admin":
         forms = Form.objects.filter(
             models.Q(pk__in=assigned_form_ids) | models.Q(created_by=request.user)
         ).order_by("-created_at").distinct()

    return render(request, 'my_forms.html', {'forms': forms})



@login_required
def view_form(request, pk):
    form_obj = get_object_or_404(Form, pk=pk)

    user = request.user
    is_admin = getattr(user, "role", None) == "admin"
    is_creator = getattr(form_obj, "created_by_id", None) == user.id
    is_assigned = FormAssignment.objects.filter(form=form_obj, user=user).exists()

    if not (is_admin or is_creator or is_assigned):
        return HttpResponseForbidden("You don't have access to this form.")

    # Has this user already submitted?
    existing_submission = None
    if not (is_admin or is_creator):  # admins/creators are not the “fillers”
        existing_submission = FormSubmission.objects.filter(form=form_obj, user=user).first()

    if request.method == "POST" and not (is_admin or is_creator):
        # Save answers atomically
        with transaction.atomic():
            submission, _created = FormSubmission.objects.get_or_create(form=form_obj, user=user)
            # (Optional) if you want to allow resubmission, you could clear old answers:
            # submission.answers.all().delete()

            questions = form_obj.questions.all()
            for q in questions:
                key = f"q_{q.id}"
                value = request.POST.get(key, "").strip()
                Answer.objects.update_or_create(
                    submission=submission,
                    question=q,
                    defaults={"value": value},
                )

            # Mark assignment as completed
            try:
                fa = FormAssignment.objects.get(form=form_obj, user=user)
                if not fa.completed:
                    fa.mark_completed()
            except FormAssignment.DoesNotExist:
                pass

        messages.success(request, "Your answers have been submitted.")
        return redirect("view_form", pk=form_obj.pk)

    context = {
        "form": form_obj,
        "existing_submission": existing_submission,
        "is_admin": is_admin,
        "is_creator": is_creator,
        "is_assigned": is_assigned,
    }
    return render(request, "form_detail.html", context)


@login_required
def personnel(request):
    users = CustomUser.objects.all().order_by("first_name", "last_name")
    return render(request, 'personnel.html', {"users": users})


@login_required
def user_profile(request, user_id):
    user_obj = get_object_or_404(CustomUser, pk=user_id)
    return render(request, "user_profile.html", {"user_obj": user_obj})

@login_required
def metrics(request):
    return render(request, "metrics.html")

@login_required
def assign_form(request, pk):
    if getattr(request.user, "role", None) != "admin":
        return HttpResponseForbidden("Admins only")

    form_obj = get_object_or_404(Form, pk=pk)

    if request.method == "POST":
        user_ids = request.POST.getlist("user_ids")  # multiple selection
        created = 0
        for uid in user_ids:
            user = get_object_or_404(CustomUser, pk=int(uid))
            _, was_created = FormAssignment.objects.get_or_create(
                form=form_obj,
                user=user,
                defaults={"assigned_by": request.user},
            )
            if was_created:
                created += 1
        messages.success(request, f"Assigned to {created} user(s).")
        return redirect("view_form", pk=form_obj.pk)

    # show only users not already assigned, ordered nicely
    assigned_user_ids = FormAssignment.objects.filter(form=form_obj).values_list("user_id", flat=True)
    available_users = CustomUser.objects.exclude(id__in=assigned_user_ids).order_by("first_name", "last_name")

    context = {
        "form_obj": form_obj,
        "available_users": available_users,
    }
    return render(request, "assign_form.html", context)

@login_required
def form_analytics(request, pk):
    if getattr(request.user, "role", None) != "admin":
        return HttpResponseForbidden("Admins only")

    form_obj = get_object_or_404(Form, pk=pk)
    assignments = FormAssignment.objects.select_related("user").filter(form=form_obj)

    total_assigned = assignments.count()
    completed = assignments.filter(completed=True)
    not_completed = assignments.filter(completed=False)

    context = {
        "form_obj": form_obj,
        "total_assigned": total_assigned,
        "completed_count": completed.count(),
        "not_completed_count": not_completed.count(),
        "completed_assignments": completed.order_by("user__first_name", "user__last_name"),
        "not_completed_assignments": not_completed.order_by("user__first_name", "user__last_name"),
    }
    return render(request, "form_analytics.html", context)
