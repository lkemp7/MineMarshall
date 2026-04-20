from django.contrib.auth.decorators import login_required
from accounts.models import CustomUser
from django.contrib import messages
from .models import Form, Question
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from .services import create_or_update_user_from_post
from django.utils import timezone
from django.contrib import messages
from django.template.loader import render_to_string
import uuid
from django.db import transaction
from django.db.models import Prefetch
from .models import FormAssignment, FormSubmission, Answer, Project, ProjectRole, ProjectInvite
from .models import Form, Question, WorkerProfile, Credential, SubmissionCredentialAttachment,LICENCE_PRESETS,LICENCE_PRESET_LABELS
from django.db.models import Count
from django.utils import timezone
from datetime import date
import secrets
from django.contrib import messages
from accounts.models import CustomUser
from .models import OnboardingInvite
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse

@login_required
def dashboard(request):
    users_with_expired = []
    today = timezone.now().date()
    
    for user in CustomUser.objects.all():
        # Filter credentials where expiry_date is in the past
        expired_creds = user.credentials.filter(
            expiry_date__lt=today,
            expiry_date__isnull=False
        )
        if expired_creds.exists():
            users_with_expired.append({
                'user': user,
                'expired_credentials': expired_creds
            })
    
    context = {
        'users_with_expired': users_with_expired,
    }
    return render(request, 'dashboard.html', context)



@login_required
def my_forms(request):
    # Only show forms created by the logged-in user
    forms = Form.objects.filter(created_by=request.user).order_by("-created_at")
    return render(request, "my_forms.html", {"forms": forms})


@login_required
def view_form(request, pk):
    form_obj = get_object_or_404(Form, pk=pk, created_by=request.user)
    questions = form_obj.questions.all().order_by('order')
    
    context = {
        'form': form_obj,
        'questions': questions,
    }
    return render(request, 'view_form.html', context)


@login_required
def personnel(request):
    users = CustomUser.objects.all().order_by("first_name", "last_name")
    return render(request, 'personnel.html', {"users": users})


@login_required
def user_profile(request, user_id):
    user_qs = CustomUser.objects.prefetch_related("credentials").select_related("worker_profile")
    user_obj = get_object_or_404(user_qs, pk=user_id)

    can_edit_credentials = (
        request.user.role in ["admin", "manager"] or request.user.pk == user_obj.pk
    )

    return render(
        request,
        "user_profile.html",
        {
            "user_obj": user_obj,
            "licence_presets": LICENCE_PRESETS,
            "can_edit_credentials": can_edit_credentials,
        },
    )

def _is_admin_or_manager(user):
    return getattr(user, "role", None) in ["admin", "manager"]


def _user_has_compliance_issue(user):
    today = timezone.localdate()
    expired_creds = user.credentials.filter(
        expiry_date__isnull=False,
        expiry_date__lt=today
    )
    return expired_creds.exists(), list(expired_creds)


def _project_member_status(invite):
    has_issue, expired_creds = _user_has_compliance_issue(invite.user)

    if invite.status != "completed":
        return "Not Submitted", has_issue, expired_creds

    if invite.review_status == "approved":
        if has_issue:
            return "Approved - Compliance Issue", has_issue, expired_creds
        return "Approved", has_issue, expired_creds

    if invite.review_status == "rejected":
        return "Rejected", has_issue, expired_creds

    return "Submitted", has_issue, expired_creds

@login_required
def metrics(request):
    if not _is_admin_or_manager(request.user):
        messages.error(request, "You do not have permission to view metrics.")
        return redirect("dashboard")

    projects = Project.objects.prefetch_related(
        Prefetch(
            "invites",
            queryset=ProjectInvite.objects.select_related(
                "user",
                "project_role",
                "project_role__required_form",
                "reviewed_by",
            ).prefetch_related("user__credentials")
        ),
        Prefetch(
            "roles",
            queryset=ProjectRole.objects.select_related("required_form")
        ),
    ).order_by("title")

    selected_project_id = request.GET.get("project")
    selected_role = request.GET.get("role", "").strip()
    sort_by = request.GET.get("sort", "name")

    selected_project = None
    role_titles = []
    member_rows = []

    totals = {
        "total_members": 0,
        "not_submitted": 0,
        "submitted": 0,
        "approved": 0,
        "pending_review": 0,
        "compliance_issues": 0,
        "rejected": 0,
        "completion_rate": 0,
    }

    project_timeline = None
    role_counts = []
    project_cards = []

    status_bar = {
        "not_submitted_percent": 0,
        "submitted_percent": 0,
        "approved_percent": 0,
        "compliance_percent": 0,
    }

    max_role_count = 0

    colour_classes = [
        "from-orange-400 to-amber-500",
        "from-sky-400 to-blue-500",
        "from-emerald-400 to-green-500",
        "from-fuchsia-400 to-purple-500",
        "from-rose-400 to-pink-500",
        "from-cyan-400 to-teal-500",
        "from-yellow-400 to-orange-500",
        "from-indigo-400 to-violet-500",
    ]

    for index, project in enumerate(projects):
        invites = list(project.invites.all())

        card_totals = {
            "total_members": 0,
            "not_submitted": 0,
            "submitted": 0,
            "approved": 0,
            "pending_review": 0,
            "compliance_issues": 0,
            "rejected": 0,
        }

        for invite in invites:
            derived_status, has_issue, expired_creds = _project_member_status(invite)

            card_totals["total_members"] += 1

            if derived_status == "Not Submitted":
                card_totals["not_submitted"] += 1
            elif derived_status == "Submitted":
                card_totals["submitted"] += 1
                card_totals["pending_review"] += 1
            elif derived_status == "Approved":
                card_totals["approved"] += 1
            elif derived_status == "Approved - Compliance Issue":
                card_totals["approved"] += 1
                card_totals["compliance_issues"] += 1
            elif derived_status == "Rejected":
                card_totals["rejected"] += 1

        project_cards.append({
            "project": project,
            "totals": card_totals,
            "colour_class": colour_classes[index % len(colour_classes)],
        })

    if selected_project_id:
        selected_project = get_object_or_404(projects, pk=selected_project_id)

        role_titles = list(
            selected_project.roles.order_by("title").values_list("title", flat=True)
        )

        invites = list(selected_project.invites.all())

        for invite in invites:
            derived_status, has_issue, expired_creds = _project_member_status(invite)

            latest_submission = None
            required_form = invite.project_role.required_form
            if required_form:
                latest_submission = (
                    FormSubmission.objects
                    .filter(form=required_form, user=invite.user)
                    .order_by("-submitted_at")
                    .first()
                )

            row = {
                "invite": invite,
                "user": invite.user,
                "role": invite.project_role.title,
                "required_form": required_form,
                "submission": latest_submission,
                "derived_status": derived_status,
                "has_compliance_issue": has_issue,
                "expired_credentials": expired_creds,
            }

            if selected_role and invite.project_role.title != selected_role:
                continue

            member_rows.append(row)

        for row in member_rows:
            totals["total_members"] += 1

            if row["derived_status"] == "Not Submitted":
                totals["not_submitted"] += 1
            elif row["derived_status"] == "Submitted":
                totals["submitted"] += 1
                totals["pending_review"] += 1
            elif row["derived_status"] == "Approved":
                totals["approved"] += 1
            elif row["derived_status"] == "Approved - Compliance Issue":
                totals["approved"] += 1
                totals["compliance_issues"] += 1
            elif row["derived_status"] == "Rejected":
                totals["rejected"] += 1

        if totals["total_members"] > 0:
            completed_count = totals["approved"] + totals["compliance_issues"]
            totals["completion_rate"] = int((completed_count / totals["total_members"]) * 100)

            status_bar["not_submitted_percent"] = int((totals["not_submitted"] / totals["total_members"]) * 100)
            status_bar["submitted_percent"] = int((totals["submitted"] / totals["total_members"]) * 100)
            status_bar["approved_percent"] = int((totals["approved"] / totals["total_members"]) * 100)
            status_bar["compliance_percent"] = int((totals["compliance_issues"] / totals["total_members"]) * 100)

        role_counts = []
        for role in selected_project.roles.all():
            role_member_count = sum(1 for row in member_rows if row["role"] == role.title)
            role_counts.append({
                "role": role.title,
                "count": role_member_count,
            })

        if role_counts:
            max_role_count = max(item["count"] for item in role_counts) or 1
            for item in role_counts:
                item["bar_percent"] = int((item["count"] / max_role_count) * 100) if max_role_count > 0 else 0

        if sort_by == "role":
            member_rows.sort(key=lambda x: (x["role"].lower(), x["user"].first_name.lower(), x["user"].last_name.lower()))
        elif sort_by == "status":
            member_rows.sort(key=lambda x: x["derived_status"].lower())
        else:
            member_rows.sort(key=lambda x: (x["user"].first_name.lower(), x["user"].last_name.lower(), x["user"].email.lower()))

        today = timezone.localdate()
        start_date = selected_project.start_date
        end_date = selected_project.end_date

        if end_date:
            total_days = max((end_date - start_date).days, 1)
            elapsed_days = max(min((today - start_date).days, total_days), 0)
            remaining_days = max((end_date - today).days, 0)
            progress_percent = int((elapsed_days / total_days) * 100) if total_days > 0 else 0
        else:
            total_days = None
            elapsed_days = max((today - start_date).days, 0)
            remaining_days = None
            progress_percent = None

        project_timeline = {
            "today": today,
            "start_date": start_date,
            "end_date": end_date,
            "total_days": total_days,
            "elapsed_days": elapsed_days,
            "remaining_days": remaining_days,
            "progress_percent": progress_percent,
        }

    context = {
        "projects": projects,
        "project_cards": project_cards,
        "selected_project": selected_project,
        "selected_project_id": selected_project_id,
        "selected_role": selected_role,
        "sort_by": sort_by,
        "role_titles": role_titles,
        "member_rows": member_rows,
        "totals": totals,
        "role_counts": role_counts,
        "project_timeline": project_timeline,
        "status_bar": status_bar,
        "max_role_count": max_role_count,
    }
    return render(request, "metrics.html", context)

@login_required
@require_POST
def update_project_invite_review_status(request, invite_id):
    if not _is_admin_or_manager(request.user):
        return HttpResponseForbidden("Permission denied")

    invite = get_object_or_404(
        ProjectInvite.objects.select_related("project"),
        pk=invite_id,
    )

    new_status = request.POST.get("review_status")
    if new_status not in ["pending_review", "approved", "rejected"]:
        messages.error(request, "Invalid review status.")
        return redirect(f"{reverse('metrics')}?project={invite.project_id}")

    invite.review_status = new_status
    invite.reviewed_by = request.user
    invite.reviewed_at = timezone.now()
    invite.save(update_fields=["review_status", "reviewed_by", "reviewed_at"])

    messages.success(request, f"{invite.user.get_full_name() or invite.user.email} marked as {invite.get_review_status_display()}.")
    return redirect(f"{reverse('metrics')}?project={invite.project_id}")


@require_POST
@login_required
def submit_authorization_form(request):
    if request.method != "POST":
        return redirect("my_forms")
    user = create_or_update_user_from_post(request.POST)
    if not user:
        return redirect("my_forms")
    return redirect("user_profile", user_id=user.id)


@login_required
def add_user(request):
    if request.user.role not in ['admin', 'manager']:
        messages.error(request, 'You do not have permission to add users.')
        return redirect('personnel')
    
    if request.method == 'POST':
        try:
            # Create user
            email = request.POST.get('email')
            
            # Check if user already exists
            if CustomUser.objects.filter(email=email).exists():
                messages.error(request, f'A user with email {email} already exists.')
                return redirect('personnel')
            
            user = CustomUser.objects.create_user(
                username=email,
                email=email,
                password=request.POST.get('password'),
                first_name=request.POST.get('first_name'),
                last_name=request.POST.get('last_name'),
                phone_number=request.POST.get('phone_number', ''),
                role=request.POST.get('role', 'user')
            )
            
            # Create worker profile if any fields are provided
            dob = request.POST.get('dob')
            worker_role = request.POST.get('worker_role')
            project = request.POST.get('project')
            employer = request.POST.get('employer')
            emergency_contact_name = request.POST.get('emergency_contact_name')
            emergency_contact_mobile = request.POST.get('emergency_contact_mobile')
            
            if any([dob, worker_role, project, employer, emergency_contact_name, emergency_contact_mobile]):
                WorkerProfile.objects.create(
                    user=user,
                    dob=dob if dob else None,
                    role=worker_role or '',
                    project=project or '',
                    employer=employer or '',
                    emergency_contact_name=emergency_contact_name or '',
                    emergency_contact_mobile=emergency_contact_mobile or ''
                )
            
            messages.success(request, f'User {user.first_name} {user.last_name} created successfully.')
            return redirect('user_profile', user_id=user.pk)
            
        except Exception as e:
            messages.error(request, f'Error creating user: {str(e)}')
            return redirect('personnel')
    
    return redirect('personnel')

@login_required
def edit_user_profile(request, pk):
    if request.user.role not in ['admin', 'manager']:
        messages.error(request, 'You do not have permission to edit profiles.')
        return redirect('personnel')
    
    user_obj = get_object_or_404(CustomUser, pk=pk)
    
    if request.method == 'POST':
        user_obj.first_name = request.POST.get('first_name')
        user_obj.last_name = request.POST.get('last_name')
        user_obj.email = request.POST.get('email')
        user_obj.phone_number = request.POST.get('phone_number')
        user_obj.save()
        
        # Update or create worker profile
        if hasattr(user_obj, 'worker_profile'):
            profile = user_obj.worker_profile
        else:
            profile = WorkerProfile.objects.create(user=user_obj)
        
        dob = request.POST.get('dob')
        profile.dob = dob if dob else None
        profile.role = request.POST.get('worker_role')
        profile.project = request.POST.get('project')
        profile.employer = request.POST.get('employer')
        profile.emergency_contact_name = request.POST.get('emergency_contact_name')
        profile.emergency_contact_mobile = request.POST.get('emergency_contact_mobile')
        profile.save()
        
        messages.success(request, f'Profile updated for {user_obj.first_name} {user_obj.last_name}')
        return redirect('user_profile', user_id=pk)
    
    return redirect('user_profile', user_id=pk)

@login_required
def save_credential(request, pk):
    user_obj = get_object_or_404(CustomUser, pk=pk)

    if request.user.role not in ['admin', 'manager'] and request.user.pk != user_obj.pk:
        messages.error(request, 'You do not have permission to edit credentials.')
        return redirect('user_profile', user_id=pk)

    if request.method == 'POST':
        credential_id = request.POST.get('credential_id')

        if credential_id:
            credential = get_object_or_404(Credential, id=credential_id, user=user_obj)
        else:
            credential = Credential(user=user_obj)

        preset = (request.POST.get('licence_preset') or '').strip()
        custom_title = (request.POST.get('custom_title') or '').strip()
        manual_title = (request.POST.get('title') or '').strip()

        if preset == "additional":
            resolved_title = custom_title or manual_title or "Additional Licence"
        elif preset and preset in LICENCE_PRESET_LABELS:
            resolved_title = LICENCE_PRESET_LABELS[preset]
        else:
            resolved_title = manual_title

        credential.title = resolved_title

        issue_date = request.POST.get('issue_date')
        credential.issue_date = issue_date if issue_date else None

        expiry_date = request.POST.get('expiry_date')
        credential.expiry_date = expiry_date if expiry_date else None

        credential.required = request.POST.get('required') == 'on'

        uploaded_image = request.FILES.get('credential_image')
        if uploaded_image:
            credential.image = uploaded_image

        credential.save()

        messages.success(request, 'Credential saved successfully')
        return redirect('user_profile', user_id=pk)

    return redirect('user_profile', user_id=pk)

@login_required
def delete_user(request, pk):
    if request.user.role not in ['admin', 'manager']:
        messages.error(request, 'You do not have permission to delete users.')
        return redirect('personnel')
    
    user_obj = get_object_or_404(CustomUser, pk=pk)
    
    # Prevent users from deleting themselves
    if user_obj.pk == request.user.pk:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('user_profile', user_id=pk)
    
    # Prevent managers from deleting admins
    if request.user.role == 'manager' and user_obj.role == 'admin':
        messages.error(request, 'Managers cannot delete admin users.')
        return redirect('user_profile', user_id=pk)
    
    if request.method == 'POST':
        user_name = f"{user_obj.first_name} {user_obj.last_name}"
        user_obj.delete()
        messages.success(request, f'User {user_name} has been deleted.')
        return redirect('personnel')
    
    return redirect('user_profile', user_id=pk)


@login_required
def add_question_field(request):
    """Returns HTML for a new question field via HTMX"""
    question_id = str(uuid.uuid4())[:8]
    
    html = f'''
    <div class="card bg-base-100 p-4 question-card">
      <div class="flex items-center justify-between mb-3">
        <h5 class="font-semibold">Question</h5>
        <button type="button" onclick="removeQuestion(this)" class="btn btn-xs btn-ghost text-error">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
          </svg>
        </button>
      </div>
      
      <div class="form-control mb-3">
        <label class="label">
          <span class="label-text">Question Text</span>
        </label>
        <input name="questions[{question_id}][text]" type="text" 
               class="input input-bordered input-sm w-full" 
               placeholder="Enter your question" required />
      </div>
      
      <div class="grid grid-cols-2 gap-3 mb-3">
        <div class="form-control">
          <label class="label">
            <span class="label-text">Type</span>
          </label>
          <select name="questions[{question_id}][type]" 
                  class="select select-bordered select-sm"
                  onchange="toggleOptions(this, '{question_id}')">
            <option value="text">Short Text</option>
            <option value="textarea">Long Text</option>
            <option value="number">Number</option>
            <option value="date">Date</option>
            <option value="time">Time</option>
            <option value="email">Email</option>
            <option value="phone">Phone Number</option>
            <option value="radio">Multiple Choice (Single)</option>
            <option value="checkbox">Multiple Choice (Multiple)</option>
            <option value="dropdown">Dropdown</option>
            <option value="file">File Upload</option>
            <option value="license_upload">Licence Image Upload</option>
          </select>
        </div>
        
        <div class="form-control">
          <label class="cursor-pointer label">
            <span class="label-text">Required</span>
            <input type="checkbox" name="questions[{question_id}][required]" 
                   class="checkbox checkbox-primary checkbox-sm" checked />
          </label>
        </div>
      </div>
      
      <div id="options-{question_id}" style="display: none;">
        <div class="form-control">
          <label class="label">
            <span class="label-text">Options (one per line)</span>
          </label>
          <textarea name="questions[{question_id}][options]" 
                    class="textarea textarea-bordered textarea-sm" 
                    placeholder="Option 1\nOption 2\nOption 3"></textarea>
        </div>
      </div>

      <div id="licence-config-{question_id}" style="display: none;">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div class="form-control">
            <label class="label">
              <span class="label-text">Licence Type</span>
            </label>
            <select name="questions[{question_id}][licence_preset]"
                    class="select select-bordered select-sm"
                    onchange="toggleLicenceCustom(this, '{question_id}')">
              <option value="driver_licence">Driver Licence</option>
              <option value="bus_licence">Bus Licence</option>
              <option value="passport">Passport</option>
              <option value="blue_card">Blue Card</option>
              <option value="forklift_licence">Forklift Licence</option>
              <option value="additional">Additional Licence</option>
            </select>
          </div>

          <div class="form-control" id="licence-custom-{question_id}" style="display:none;">
            <label class="label">
              <span class="label-text">Custom Licence Label</span>
            </label>
            <input name="questions[{question_id}][custom_licence_label]"
                   type="text"
                   class="input input-bordered input-sm"
                   placeholder="e.g. White Card" />
          </div>
        </div>
      </div>
    </div>
    '''
    return HttpResponse(html)

@login_required
def create_form(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        questions_data = {}

        for key, value in request.POST.items():
            if key.startswith('questions['):
                parts = key.replace('questions[', '').replace(']', '').split('[')
                if len(parts) >= 2:
                    question_id = parts[0]
                    field_name = parts[1]

                    if question_id not in questions_data:
                        questions_data[question_id] = {}

                    questions_data[question_id][field_name] = value

        form = Form.objects.create(
            title=title,
            description=description,
            created_by=request.user
        )

        order = 1
        for uuid, data in questions_data.items():
            if 'text' in data and data['text']:
                question_type = data.get('type', 'text')
                options_text = data.get('options', '')

                if question_type == 'license_upload':
                    preset = data.get('licence_preset', '')
                    custom_label = (data.get('custom_licence_label', '') or '').strip()

                    if preset == 'additional':
                        options_text = custom_label or 'Additional Licence'
                    else:
                        options_text = LICENCE_PRESET_LABELS.get(preset, 'Licence')

                Question.objects.create(
                    form=form,
                    question_text=data.get('text', ''),
                    question_type=question_type,
                    options_text=options_text,
                    is_required=data.get('required') == 'on',
                    order=order
                )
                order += 1

        messages.success(request, f'Form "{title}" created successfully!')
        return redirect('my_forms')

    return render(request, 'create_form.html')

@login_required
def delete_form(request, pk):
    if request.user.role not in ['admin', 'manager']:
        messages.error(request, 'You do not have permission to delete forms.')
        return redirect('my_forms')
    
    form_obj = get_object_or_404(Form, pk=pk, created_by=request.user)
    
    if request.method == 'POST':
        form_title = form_obj.title
        form_obj.delete()
        messages.success(request, f'Form "{form_title}" has been deleted.')
        return redirect('my_forms')
    
    return redirect('my_forms')

@login_required
def edit_form_data(request, pk):
    """Return form data as JSON for editing"""
    if request.user.role not in ['admin', 'manager']:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    form_obj = get_object_or_404(Form, pk=pk, created_by=request.user)
    questions = form_obj.questions.all().order_by('order')
    
    data = {
        'id': form_obj.pk,
        'title': form_obj.title,
        'description': form_obj.description,
                'questions': [
            {
                'text': q.question_text,
                'type': q.question_type,
                'options': q.options_text,
                'required': q.is_required,
            }
            for q in questions
        ]
    }
    
    return JsonResponse(data)

@login_required
def update_form(request, pk):
    if request.user.role not in ['admin', 'manager']:
        return HttpResponse(status=403)
    
    form_obj = get_object_or_404(Form, pk=pk, created_by=request.user)
    
    if request.method == 'POST':
        # Update basic info
        form_obj.title = request.POST.get('title', 'Untitled Form')
        form_obj.description = request.POST.get('description', '')
        form_obj.save()
        
        # Delete existing questions
        form_obj.questions.all().delete()
        
        # Process questions (same as create)
        questions_data = {}
        for key, value in request.POST.items():
            if key.startswith('questions['):
                parts = key.split('[')
                if len(parts) >= 3:
                    uuid = parts[1].rstrip(']')
                    field = parts[2].rstrip(']')
                    
                    if uuid not in questions_data:
                        questions_data[uuid] = {}
                    questions_data[uuid][field] = value
        
    order = 1
    for uuid, data in questions_data.items():
        if 'text' in data and data['text']:
            question_type = data.get('type', 'text')
            options_text = data.get('options', '')

            if question_type == 'license_upload':
                preset = data.get('licence_preset', '')
                custom_label = (data.get('custom_licence_label', '') or '').strip()

                if preset == 'additional':
                    options_text = custom_label or 'Additional Licence'
                else:
                    options_text = LICENCE_PRESET_LABELS.get(preset, 'Licence')

            Question.objects.create(
                form=form_obj,
                question_text=data.get('text', ''),
                question_type=question_type,
                options_text=options_text,
                is_required=data.get('required') == 'on',
                order=order
            )
            order += 1
        
        messages.success(request, f'Form "{form_obj.title}" updated successfully!')
        
        # Reset modal state via JavaScript
        response = HttpResponse()
        response['HX-Redirect'] = '/dashboard/forms/mine/'
        return response
    
    return HttpResponse(status=405)

### Project setup

def _is_admin_or_manager(user):
    return getattr(user, "role", None) in ["admin", "manager"]


@login_required
def projects_home(request):
    """Single sidebar entry point: admin/manager sees admin projects, user sees invites."""
    if _is_admin_or_manager(request.user):
        return redirect("projects")
    return redirect("my_projects")


@login_required
def projects(request):
    """Admin/Manager project list + create."""
    if not _is_admin_or_manager(request.user):
        messages.error(request, "You do not have permission to view projects.")
        return redirect("dashboard")

    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        description = (request.POST.get("description") or "").strip()
        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date") or None

        if not title:
            messages.error(request, "Project title is required.")
            return redirect("projects")

        if not start_date:
            messages.error(request, "Project start date is required.")
            return redirect("projects")

        if end_date and end_date < start_date:
            messages.error(request, "End date cannot be before start date.")
            return redirect("projects")

        project = Project.objects.create(
            title=title,
            description=description,
            start_date=start_date,
            end_date=end_date,
            created_by=request.user,
        )
        messages.success(request, f'Project "{project.title}" created successfully.')
        return redirect("project_detail", pk=project.pk)

    projects_qs = Project.objects.all().prefetch_related("roles").order_by("-created_at")
    return render(request, "projects.html", {"projects": projects_qs})


@login_required
def project_detail(request, pk):
    """Admin/Manager page to manage project roles, forms, and invites."""
    if not _is_admin_or_manager(request.user):
        messages.error(request, "You do not have permission to manage projects.")
        return redirect("dashboard")

    project = get_object_or_404(
        Project.objects.prefetch_related(
            Prefetch("roles", queryset=ProjectRole.objects.select_related("required_form")),
            Prefetch("invites", queryset=ProjectInvite.objects.select_related("user", "project_role", "project_role__required_form")),
        ),
        pk=pk,
    )

    forms = Form.objects.filter(is_active=True).order_by("title")
    users = CustomUser.objects.all().order_by("first_name", "last_name", "email")

    return render(
        request,
        "project_detail.html",
        {
            "project": project,
            "forms": forms,
            "users": users,
        },
    )


@login_required
@require_POST
def add_project_role(request, pk):
    if not _is_admin_or_manager(request.user):
        return HttpResponseForbidden("Permission denied")

    project = get_object_or_404(Project, pk=pk)
    title = (request.POST.get("role_title") or "").strip()
    form_id = request.POST.get("required_form_id") or None

    if not title:
        messages.error(request, "Role title is required.")
        return redirect("project_detail", pk=project.pk)

    required_form = None
    if form_id:
        required_form = get_object_or_404(Form, pk=form_id)

    role_obj, created = ProjectRole.objects.get_or_create(
        project=project,
        title=title,
        defaults={"required_form": required_form},
    )

    if not created:
        # If role exists, optionally update form
        role_obj.required_form = required_form
        role_obj.save()
        messages.success(request, f'Updated role "{role_obj.title}".')
    else:
        messages.success(request, f'Added role "{role_obj.title}".')

    return redirect("project_detail", pk=project.pk)


@login_required
@require_POST
def update_project_role_form(request, project_pk, role_pk):
    if not _is_admin_or_manager(request.user):
        return HttpResponseForbidden("Permission denied")

    role_obj = get_object_or_404(ProjectRole, pk=role_pk, project_id=project_pk)
    form_id = request.POST.get("required_form_id") or None

    if form_id:
        role_obj.required_form = get_object_or_404(Form, pk=form_id)
    else:
        role_obj.required_form = None

    role_obj.save()
    messages.success(request, f'Updated required form for role "{role_obj.title}".')
    return redirect("project_detail", pk=project_pk)


@login_required
@require_POST
def invite_users_to_project_role(request, project_pk, role_pk):
    if not _is_admin_or_manager(request.user):
        return HttpResponseForbidden("Permission denied")

    role_obj = get_object_or_404(
        ProjectRole.objects.select_related("project", "required_form"),
        pk=role_pk,
        project_id=project_pk,
    )

    user_ids = request.POST.getlist("user_ids")
    if not user_ids:
        messages.error(request, "Please select at least one user to invite.")
        return redirect("project_detail", pk=project_pk)

    created_count = 0
    updated_count = 0

    with transaction.atomic():
        for uid in user_ids:
            user = CustomUser.objects.filter(pk=uid).first()
            if not user:
                continue

            invite, created = ProjectInvite.objects.get_or_create(
                project=role_obj.project,
                project_role=role_obj,
                user=user,
                defaults={"invited_by": request.user, "status": "pending"},
            )

            if created:
                created_count += 1
            else:
                # Refresh existing invite back to pending if re-inviting (unless completed)
                if invite.status != "completed":
                    invite.status = "pending"
                    invite.invited_by = request.user
                    invite.viewed_at = None
                    invite.save()
                    updated_count += 1

            # If role has a required form, create/ensure assignment exists
            if role_obj.required_form:
                FormAssignment.objects.get_or_create(
                    form=role_obj.required_form,
                    user=user,
                    defaults={"assigned_by": request.user},
                )

    msg_parts = []
    if created_count:
        msg_parts.append(f"{created_count} invite(s) sent")
    if updated_count:
        msg_parts.append(f"{updated_count} invite(s) re-sent")
    if not msg_parts:
        msg_parts.append("No new invites were created")

    messages.success(request, f"{' and '.join(msg_parts)} for role {role_obj.title}.")
    return redirect("project_detail", pk=project_pk)


@login_required
def my_projects(request):
    """User-facing invites list."""
    invites = (
        ProjectInvite.objects
        .filter(user=request.user)
        .select_related("project", "project_role", "project_role__required_form")
        .order_by("-invited_at")
    )
    return render(request, "my_projects.html", {"invites": invites})


@login_required
def project_invite_form(request, invite_id):
    invite = get_object_or_404(
        ProjectInvite.objects.select_related("project", "project_role", "project_role__required_form", "user"),
        pk=invite_id,
        user=request.user,
    )

    required_form = invite.project_role.required_form
    if not required_form:
        messages.error(request, "No required form has been configured for this role yet.")
        return redirect("my_projects")

    if invite.status == "pending":
        invite.status = "viewed"
        invite.viewed_at = timezone.now()
        invite.save(update_fields=["status", "viewed_at"])

    questions = required_form.questions.all().order_by("order")

    if request.method == "POST":
        with transaction.atomic():
            submission = FormSubmission.objects.create(
                form=required_form,
                user=request.user,
            )

            for q in questions:
                key = f"question_{q.id}"
                uploaded_file = request.FILES.get(key)

                if q.question_type == "checkbox":
                    values = request.POST.getlist(key)
                    answer_value = ", ".join(values)
                elif q.question_type in ["file", "license_upload"]:
                    answer_value = q.options_text if q.question_type == "license_upload" else ""
                else:
                    answer_value = request.POST.get(key, "")

                if q.is_required:
                    if q.question_type in ["file", "license_upload"] and not uploaded_file:
                        messages.error(request, f'Question "{q.question_text}" is required.')
                        submission.delete()
                        return redirect("project_invite_form", invite_id=invite.id)
                    if q.question_type not in ["file", "license_upload"] and not answer_value:
                        messages.error(request, f'Question "{q.question_text}" is required.')
                        submission.delete()
                        return redirect("project_invite_form", invite_id=invite.id)

                Answer.objects.create(
                    submission=submission,
                    question=q,
                    answer_text=answer_value or "",
                    answer_file=uploaded_file if uploaded_file else None,
                )

            # Automatically attach all additional profile licences to every submission
            additional_credentials = request.user.credentials.filter(required=False, image__isnull=False)
            for cred in additional_credentials:
                SubmissionCredentialAttachment.objects.create(
                    submission=submission,
                    source_credential=cred,
                    title=cred.title,
                    image=cred.image,
                )

            invite.status = "completed"
            invite.completed_at = timezone.now()
            invite.save(update_fields=["status", "completed_at"])

            FormAssignment.objects.filter(form=required_form, user=request.user).update(
                completed=True,
                completed_at=timezone.now(),
            )

        messages.success(request, f'Form "{required_form.title}" submitted successfully.')
        return redirect("my_projects")

    return render(
        request,
        "project_invite_form.html",
        {
            "invite": invite,
            "form_obj": required_form,
            "questions": questions,
        },
    )

@login_required
def start_induction(request):
    if request.user.role not in ["admin", "manager"]:
        messages.error(request, "You do not have permission to start an induction.")
        return redirect("dashboard")
    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        requires_default_form = request.POST.get("requires_default_form") == "on"

        if not first_name or not last_name or not email:
            messages.error(request, "First name, last name, and email are required.")
            return redirect("personnel")

        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, "A user with that email already exists.")
            return redirect("personnel")

        user = CustomUser.objects.create(
            email=email,
            username=email,
            first_name=first_name,
            last_name=last_name,
            is_active=False,
        )
        user.set_unusable_password()
        user.save()

        invite = OnboardingInvite.objects.create(
            user=user,
            email=email,
            first_name=first_name,
            last_name=last_name,
            token=secrets.token_urlsafe(32),
            requires_default_form=requires_default_form,
            status="sent",
        )

        setup_path = reverse("setup_account", kwargs={"token": invite.token})
        setup_url = request.build_absolute_uri(setup_path)
        #error debugging
        print("EMAIL_BACKEND =", settings.EMAIL_BACKEND)
        
        send_mail(
            subject="Complete your MineMarshall account setup",
            message=(
                f"Hello {first_name},\n\n"
                f"You have been invited to set up your MineMarshall account.\n\n"
                f"Use the link below to create your password and continue onboarding:\n\n"
                f"{setup_url}\n\n"
                f"If your induction requires it, you will be taken to the Default Form after setup."
            ),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@minemarshall.local"),
            recipient_list=[email],
            fail_silently=False,
        )

        messages.success(
            request,
            f"Induction started for {email}. Setup link: {setup_url}"
        )
        return redirect("personnel")

    return redirect("personnel")

@login_required
def onboarding_default_form(request, token):
    invite = get_object_or_404(OnboardingInvite, token=token)
    user = invite.user

    if request.user != user:
        messages.error(request, "You must complete onboarding from your invited account.")
        return redirect("login")

    if invite.status == "completed":
        return redirect("dashboard")

    if request.method == "POST":
        post_data = request.POST.copy()

        # Lock identity fields to the inducted user
        post_data["email"] = user.email
        post_data["first_name"] = user.first_name
        post_data["last_name"] = user.last_name

        create_or_update_user_from_post(post_data)

        invite.status = "completed"
        invite.completed_at = timezone.now()
        invite.save()

        messages.success(request, "Default form completed successfully.")
        return redirect("dashboard")

    ocr_data = request.session.pop(f"licence_ocr_{token}", {})
    context = {
        "invite": invite,
        "user_obj": user,
        "ocr_dob": ocr_data.get("dob") or "",
        "ocr_licence_number": ocr_data.get("licence_number") or "",
    }
    return render(request, "forms/onboarding_default_form.html", context)