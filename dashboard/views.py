from django.contrib.auth.decorators import login_required
from django.db import models
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
from django.db import transaction, IntegrityError
from django.db.models import Prefetch
from .models import FormAssignment, FormSubmission, Answer, Project, ProjectRole, ProjectInvite, ApprovalDocument
from .models import Form, Question, WorkerProfile, Credential, FormDraft, SubmissionCredentialAttachment,LICENCE_PRESETS,LICENCE_PRESET_LABELS
from django.db.models import Count, Q
from django.utils import timezone
from datetime import date
import secrets
from django.contrib import messages
from accounts.models import CustomUser
from .models import OnboardingInvite
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.db.models import Prefetch

@login_required
def dashboard(request):
    """Render the main dashboard with project overview cards and a project attention panel.

    For admin/manager users, builds two datasets:
      - dashboard_project_cards: per-project member status counts and timeline progress
        percentages, displayed as cards in the left panel.
      - project_member_issues: every invite that has a problem (not submitted, pending
        review, rejected, or a compliance issue), shown in the right attention panel.

    Regular users see an empty dashboard (the template handles the display).

    Context:
        dashboard_project_cards (list[dict]): Project cards with totals, status bar
            percentages, and timeline data.
        project_member_issues (list[dict]): Invite rows with problem descriptions and
            a primary_problem key used to drive badge colours.

    Template: dashboard.html
    """
    today = timezone.localdate()

    dashboard_project_cards = []

    if _is_admin_or_manager(request.user):
        projects = (
            Project.objects
            .prefetch_related(
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
            )
            .order_by("title")
        )

        for project in projects:
            invites = list(project.invites.all())

            totals = {
                "total_members": 0,
                "not_submitted": 0,
                "pending_review": 0,
                "approved": 0,
                "compliance_issues": 0,
                "rejected": 0,
            }

            for invite in invites:
                derived_status, has_issue, expired_creds = _project_member_status(invite)

                totals["total_members"] += 1

                if derived_status == "Not Submitted":
                    totals["not_submitted"] += 1

                elif derived_status == "Submitted":
                    totals["pending_review"] += 1

                elif derived_status == "Approved":
                    totals["approved"] += 1

                elif derived_status == "Approved - Compliance Issue":
                    totals["compliance_issues"] += 1

                elif derived_status == "Rejected":
                    totals["rejected"] += 1

            status_bar = {
                "not_submitted_percent": 0,
                "pending_review_percent": 0,
                "approved_percent": 0,
                "compliance_percent": 0,
            }

            if totals["total_members"] > 0:
                status_bar["not_submitted_percent"] = int(
                    (totals["not_submitted"] / totals["total_members"]) * 100
                )
                status_bar["pending_review_percent"] = int(
                    (totals["pending_review"] / totals["total_members"]) * 100
                )
                status_bar["approved_percent"] = int(
                    (totals["approved"] / totals["total_members"]) * 100
                )
                status_bar["compliance_percent"] = int(
                    (totals["compliance_issues"] / totals["total_members"]) * 100
                )

            start_date = project.start_date
            end_date = project.end_date

            if end_date:
                total_days = max((end_date - start_date).days, 1)
                elapsed_days = max(min((today - start_date).days, total_days), 0)
                remaining_days = max((end_date - today).days, 0)
                progress_percent = int((elapsed_days / total_days) * 100)
            else:
                total_days = None
                elapsed_days = max((today - start_date).days, 0)
                remaining_days = None
                progress_percent = None

            dashboard_project_cards.append({
                "project": project,
                "totals": totals,
                "status_bar": status_bar,
                "timeline": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "total_days": total_days,
                    "elapsed_days": elapsed_days,
                    "remaining_days": remaining_days,
                    "progress_percent": progress_percent,
                },
            })

    project_member_issues = []

    if _is_admin_or_manager(request.user):
        project_invites = (
            ProjectInvite.objects
            .select_related(
                "project",
                "project_role",
                "project_role__required_form",
                "user",
            )
            .prefetch_related("user__credentials")
            .order_by("project__title", "project_role__title", "user__first_name", "user__last_name")
        )

        for invite in project_invites:
            derived_status, has_issue, expired_creds = _project_member_status(invite)

            required_form = invite.project_role.required_form
            latest_submission = None

            if required_form:
                latest_submission = (
                    FormSubmission.objects
                    .filter(
                        form=required_form,
                        user=invite.user
                    )
                    .order_by("-submitted_at")
                    .first()
                )

            problems = []
            primary_problem = None

            if invite.status != "completed":
                problems.append("Required form not submitted")
                primary_problem = "not_submitted"

            elif invite.review_status == "pending_review":
                problems.append("Submitted but not approved")
                primary_problem = "pending_review"

            elif invite.review_status == "rejected":
                problems.append("Submission rejected")
                primary_problem = "rejected"

            if has_issue:
                credential_names = ", ".join([cred.title for cred in expired_creds])
                problems.append(f"Compliance issue: expired {credential_names}")

                if primary_problem is None:
                    primary_problem = "compliance"

            if problems:
                project_member_issues.append({
                    "invite": invite,
                    "project": invite.project,
                    "user": invite.user,
                    "role": invite.project_role.title,
                    "required_form": required_form,
                    "submission": latest_submission,
                    "problems": problems,
                    "primary_problem": primary_problem,
                })

    context = {
        "dashboard_project_cards": dashboard_project_cards,
        "project_member_issues": project_member_issues,
    }

    return render(request, "dashboard.html", context)



@login_required
def my_forms(request):
    """List all forms created by the current admin/manager user.

    Restricted to admin and manager roles. Redirects non-authorised users to
    the dashboard with an error message.

    Context:
        forms (QuerySet[Form]): Forms created by the current user, newest first.

    Template: my_forms.html
    """
    if not _is_admin_or_manager(request.user):
        messages.error(request, "You do not have permission to view forms.")
        return redirect("dashboard")

    forms = Form.objects.filter(created_by=request.user).order_by("-created_at")
    return render(request, "my_forms.html", {"forms": forms})


@login_required
def view_form(request, pk):
    """Display a read-only preview of a form and its questions.

    Only the form's creator (who must also be admin/manager) may access this view.

    Args:
        pk (int): Primary key of the Form to display.

    Context:
        form (Form): The form instance.
        questions (QuerySet[Question]): Questions ordered by their display order.

    Template: view_form.html
    """
    if not _is_admin_or_manager(request.user):
        messages.error(request, "You do not have permission to view forms.")
        return redirect("dashboard")

    form_obj = get_object_or_404(Form, pk=pk, created_by=request.user)
    questions = form_obj.questions.all().order_by("order")

    context = {
        "form": form_obj,
        "questions": questions,
    }
    return render(request, "view_form.html", context)


@login_required
def personnel(request):
    """List all users with optional search filtering.

    Accepts a ?q= query parameter to filter users by first name, last name,
    email, or phone number (case-insensitive, partial match).

    Context:
        users (QuerySet[CustomUser]): All users (or filtered subset), ordered
            by first name then last name.
        search_query (str): The current search term (empty string if none).

    Template: personnel.html
    """
    search_query = request.GET.get("q", "").strip()

    users = CustomUser.objects.all().order_by("first_name", "last_name")

    if search_query:
        users = users.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone_number__icontains=search_query)
        )

    return render(
        request,
        "personnel.html",
        {
            "users": users,
            "search_query": search_query,
        },
    )


@login_required
def user_profile(request, user_id):
    """Display a worker's profile page with credentials and worker profile details.

    Access rules:
      - Admin/manager users can view any profile.
      - Regular users can only view their own profile.
      - Managers cannot view other admin or manager profiles.

    Args:
        user_id (int): Primary key of the user whose profile to display.

    Context:
        user_obj (CustomUser): The profile owner, with credentials and worker_profile
            pre-fetched to avoid N+1 queries.
        licence_presets (list): Available credential preset options for the add-credential form.
        can_edit_credentials (bool): Whether the viewer may add/edit credentials.
        can_edit_profile (bool): Whether the viewer may edit profile fields.
        is_self_profile (bool): True when the viewer is viewing their own profile.

    Template: user_profile.html
    """
    user_qs = CustomUser.objects.prefetch_related("credentials").select_related("worker_profile")
    user_obj = get_object_or_404(user_qs, pk=user_id)

    if not _is_admin_or_manager(request.user) and request.user.pk != user_obj.pk:
        return HttpResponseForbidden("Access Denied")

    if request.user.role == "manager" and user_obj.role not in ["user"] and request.user.pk != user_obj.pk:
        messages.error(request, 'You do not have permission to view admin/manager profiles.')
        return redirect('personnel')

    can_edit_credentials = (
        request.user.role in ["admin", "manager"] or request.user.pk == user_obj.pk
    )
    can_edit_profile = (
        request.user.role in ["admin", "manager"] or request.user.pk == user_obj.pk
    )
    is_self_profile = request.user.pk == user_obj.pk

    return render(
        request,
        "user_profile.html",
        {
            "user_obj": user_obj,
            "licence_presets": LICENCE_PRESETS,
            "can_edit_credentials": can_edit_credentials,
            "can_edit_profile": can_edit_profile,
            "is_self_profile": is_self_profile,
        },
    )

def _is_admin_or_manager(user):
    """Return True if the user holds the admin or manager role, or is a superuser.

    Args:
        user (CustomUser): The user to check.

    Returns:
        bool: True if the user has elevated permissions.
    """
    return getattr(user, "role", None) in ["admin", "manager"] or user.is_superuser


def _user_has_compliance_issue(user):
    """Check whether a user has any expired credentials.

    Args:
        user (CustomUser): The user whose credentials to check. Must have the
            'credentials' relation already prefetched to avoid extra queries.

    Returns:
        tuple[bool, list[Credential]]: (has_issue, expired_credentials)
    """
    today = timezone.localdate()
    expired_creds = user.credentials.filter(
        expiry_date__isnull=False,
        expiry_date__lt=today
    )
    return expired_creds.exists(), list(expired_creds)


def _project_member_status(invite):
    """Derive a human-readable status string for a project member's invite.

    Combines the invite's submission status with the user's compliance state
    to produce one of:
      - "Not Submitted"
      - "Submitted"  (pending review)
      - "Approved"
      - "Approved - Compliance Issue"
      - "Rejected"

    Args:
        invite (ProjectInvite): The invite to evaluate. The invite's user must
            have credentials prefetched.

    Returns:
        tuple[str, bool, list[Credential]]:
            (derived_status, has_compliance_issue, expired_credentials)
    """
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


def _get_invite_approval_documents(invite):
    """Fetch all active ApprovalDocuments relevant to a given invite.

    Returns documents scoped to the project, the invite's role, or the
    specific user, ordered by scope then title.

    Args:
        invite (ProjectInvite): The invite to fetch documents for.

    Returns:
        QuerySet[ApprovalDocument]: Active documents visible to this invite.
    """
    return ApprovalDocument.objects.filter(
        project=invite.project,
        is_active=True,
    ).filter(
        models.Q(scope="project") |
        models.Q(scope="role", role=invite.project_role) |
        models.Q(scope="user", target_user=invite.user)
    ).order_by("scope", "title")
    
@login_required
def metrics(request):
    """Display detailed project metrics with filtering and per-member status rows.

    Accepts three optional GET parameters:
      - project: the project ID to drill into
      - role:    filter member rows to a specific role title
      - sort:    sort member rows by "name" (default), "role", or "status"

    When no project is selected, renders overview cards for all projects.
    When a project is selected, also computes role membership counts, a status
    bar, completion rate, and a project timeline for the detail panels.

    Context:
        projects, project_cards, selected_project, selected_project_id,
        selected_role, sort_by, role_titles, member_rows, totals, role_counts,
        project_timeline, status_bar, max_role_count.

    Template: metrics.html
    """
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
    """Update the admin review status of a project invite (approve/reject/reset).

    Expects POST fields:
      - review_status: one of "approved", "rejected", "pending_review"
      - rejection_reason: required when review_status is "rejected"
      - allow_reapply: optional checkbox, "on" if the worker may resubmit
      - next: optional URL to redirect to after the action

    Args:
        invite_id (int): Primary key of the ProjectInvite to update.

    Returns:
        HttpResponse: Redirect to the next URL (referer or project submissions page).
    """
    if not _is_admin_or_manager(request.user):
        return HttpResponseForbidden("Permission denied")

    invite = get_object_or_404(
        ProjectInvite.objects.select_related("project"),
        pk=invite_id,
    )

    new_status = request.POST.get("review_status")
    next_url = (
        request.POST.get("next")
        or request.META.get("HTTP_REFERER")
        or reverse("project_submissions", args=[invite.project_id])
    )

    if new_status not in ["pending_review", "approved", "rejected"]:
        messages.error(request, "Invalid review status.")
        return redirect(next_url)

    if new_status == "approved":
        invite.review_status = "approved"
        invite.reviewed_by = request.user
        invite.reviewed_at = timezone.now()
        invite.rejection_reason = ""
        invite.allow_reapply = False
        invite.save(update_fields=[
            "review_status",
            "reviewed_by",
            "reviewed_at",
            "rejection_reason",
            "allow_reapply",
        ])
        messages.success(
            request,
            f"{invite.user.get_full_name() or invite.user.email} marked as Approved."
        )
        return redirect(next_url)

    if new_status == "rejected":
        rejection_reason = (request.POST.get("rejection_reason") or "").strip()
        allow_reapply = request.POST.get("allow_reapply") == "on"

        if not rejection_reason:
            messages.error(request, "A rejection reason is required.")
            return redirect(next_url)

        invite.review_status = "rejected"
        invite.reviewed_by = request.user
        invite.reviewed_at = timezone.now()
        invite.rejection_reason = rejection_reason
        invite.allow_reapply = allow_reapply
        invite.save(update_fields=[
            "review_status",
            "reviewed_by",
            "reviewed_at",
            "rejection_reason",
            "allow_reapply",
        ])

        messages.success(
            request,
            f"{invite.user.get_full_name() or invite.user.email} marked as Rejected."
        )
        return redirect(next_url)

    invite.review_status = "pending_review"
    invite.reviewed_by = request.user
    invite.reviewed_at = timezone.now()
    invite.save(update_fields=["review_status", "reviewed_by", "reviewed_at"])
    messages.success(request, "Review status updated.")
    return redirect(next_url)

@require_POST
@login_required
def submit_authorization_form(request):
    """Process a submitted authorisation form and upsert the corresponding user record.

    Delegates all field parsing and database writes to create_or_update_user_from_post.
    On success redirects to the upserted user's profile page.

    Returns:
        HttpResponse: Redirect to the user profile or back to my_forms if parsing fails.
    """
    if request.method != "POST":
        return redirect("my_forms")
    user = create_or_update_user_from_post(request.POST)
    if not user:
        return redirect("my_forms")
    return redirect("user_profile", user_id=user.id)


@login_required
def add_user(request):
    """Create a new user account directly (without the onboarding email flow).

    POST-only in practice (GET redirects to personnel). Validates that the email
    is not already taken, creates a CustomUser with an optional WorkerProfile,
    then redirects to the new user's profile page.

    Restricted to admin and manager roles.

    Returns:
        HttpResponse: Redirect to the new user's profile on success, or back
            to personnel on error.
    """
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
    """Save edits to a user's profile and worker profile via an HTMX form.

    On success, responds with HTTP 204 and an HX-Redirect header so the HTMX
    modal closes and the page reloads without a full navigation. Returns an
    inline HTML error fragment if the email is already in use.

    Managers may not edit admin or manager profiles other than their own.

    Args:
        pk (int): Primary key of the user to edit.

    Returns:
        HttpResponse: 204 with HX-Redirect on success, inline error HTML on
            IntegrityError, or redirect on permission failure.
    """
    if not _is_admin_or_manager(request.user) and request.user.pk != pk:
        messages.error(request, 'You do not have permission to edit profiles.')
        return redirect('personnel')
    
    user_obj = get_object_or_404(CustomUser, pk=pk)
    
    if request.user.role == "manager" and user_obj.role not in ["user"]:
        messages.error(request, 'You do not have permission to edit admin/manager profiles.')
        return redirect('personnel')
                
    
    if request.method == 'POST':
        user_obj.first_name = request.POST.get('first_name')
        user_obj.last_name = request.POST.get('last_name')
        user_obj.email = request.POST.get('email')
        user_obj.phone_number = request.POST.get('phone_number')
        if request.FILES.get("profile_picture"):
            user_obj.profile_picture = request.FILES["profile_picture"]
        try:
            with transaction.atomic():
                user_obj.save()
        except IntegrityError:
            return HttpResponse('<div class="alert alert-error"><span>That email address is already in use.</span></div>')
        
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
        
        try:
            with transaction.atomic():
                profile.save()
        except IntegrityError:
            return HttpResponse('<div class="alert alert-error"><span>That email address is already in use.</span></div>')
        
        messages.success(request, f'Profile updated for {user_obj.first_name} {user_obj.last_name}')
        response = HttpResponse(status=204)
        response['HX-Redirect'] = reverse('user_profile', kwargs={'user_id': pk})
        return response
    
    return redirect('user_profile', user_id=pk)


@login_required
def save_credential(request, pk):
    """Add or update a credential record for a user.

    Handles both the "add new" (no credential_id in POST) and "edit existing"
    cases. Resolves the credential title from a preset dropdown, a custom label
    for additional licences, or a manual text input.

    Admin/manager users may edit any user's credentials. Regular users may only
    edit their own.

    Args:
        pk (int): Primary key of the user whose credential to save.

    Returns:
        HttpResponse: Redirect to the user's profile page.
    """
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
    """Delete a user account. POST-only in practice; GET redirects to their profile.

    Guards:
      - Admin/manager only.
      - Users cannot delete their own account.
      - Managers cannot delete admin accounts.

    Args:
        pk (int): Primary key of the user to delete.

    Returns:
        HttpResponse: Redirect to personnel list on success, or to the user
            profile with an error message if a guard fails.
    """
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
    """Return an HTML fragment for a new question card, injected by HTMX into the form builder.

    Generates a unique 8-character ID for the question to namespace its form
    fields (e.g. questions[abc12345][text]). Includes conditional sections for
    options (radio/checkbox/dropdown) and licence configuration (licence_upload).

    Returns:
        HttpResponse: Raw HTML string of the question card fragment.
    """
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
            <option value="licence_upload">Licence Image Upload</option>
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
    """Create a new Form with its associated Questions from the form builder POST.

    Question fields are submitted with bracket notation keys
    (e.g. questions[<uuid>][text]) which are parsed into a dict keyed by the
    temporary UUID. For licence_upload questions, the licence preset or custom
    label is stored in options_text rather than a multi-line options string.

    On success responds with HTTP 200 and an HX-Redirect header to return the
    HTMX request to the my_forms page.

    Returns:
        HttpResponse: HX-Redirect response on success, or a render of create_form.html on GET.
    """
    if not _is_admin_or_manager(request.user):
        return HttpResponseForbidden("User is not admin/manager")
    
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

                if question_type == 'licence_upload':
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
        response = HttpResponse()
        response['HX-Redirect'] = '/dashboard/forms/mine/'
        return response

    return render(request, 'create_form.html')

@login_required
def delete_form(request, pk):
    """Delete a form. POST-only in practice; GET redirects to my_forms.

    Only the form's creator (who must be admin/manager) may delete it.

    Args:
        pk (int): Primary key of the Form to delete.

    Returns:
        HttpResponse: Redirect to my_forms on success or permission failure.
    """
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
    """Return a form's metadata and questions as JSON, used to populate the edit modal.

    Called by the JavaScript edit modal to pre-fill the form builder fields
    before showing the modal to the user.

    Args:
        pk (int): Primary key of the Form to serialise.

    Returns:
        JsonResponse: {id, title, description, questions: [{text, type, options, required}]}
    """
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
    """Replace a form's questions with the updated set submitted from the edit modal.

    Deletes all existing questions and recreates them from the POST data,
    applying the same bracket-notation parsing used in create_form. This is
    a full replace rather than a diff to keep the logic simple.

    Args:
        pk (int): Primary key of the Form to update.

    Returns:
        HttpResponse: HX-Redirect on success, 403 on permission failure, 405 on GET.
    """
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

                if question_type == 'licence_upload':
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


@login_required
def projects_home(request):
    """Single sidebar entry point: admin/manager sees admin projects, user sees invites."""
    if _is_admin_or_manager(request.user):
        return redirect("projects")
    return redirect("my_projects")


@login_required
def projects(request):
    """List all projects and handle project creation for admin/manager users.

    GET  - renders the projects list.
    POST - validates and creates a new Project, then redirects to its detail page.

    Validation includes date range checks (years 1900-2099) and ensures the
    end date is not before the start date.

    Context:
        projects (QuerySet[Project]): All projects with roles prefetched,
            ordered newest first.

    Template: projects.html
    """
    if not _is_admin_or_manager(request.user):
        messages.error(request, "You do not have permission to view projects.")
        return redirect("dashboard")

    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        description = (request.POST.get("description") or "").strip()
        start_date_raw = (request.POST.get("start_date") or "").strip()
        end_date_raw = (request.POST.get("end_date") or "").strip()

        if not title:
            messages.error(request, "Project title is required.")
            return redirect("projects")

        if not start_date_raw:
            messages.error(request, "Project start date is required.")
            return redirect("projects")

        try:
            start_date = date.fromisoformat(start_date_raw)
        except ValueError:
            messages.error(request, "Please enter a valid project start date.")
            return redirect("projects")

        end_date = None
        if end_date_raw:
            try:
                end_date = date.fromisoformat(end_date_raw)
            except ValueError:
                messages.error(request, "Please enter a valid project end date.")
                return redirect("projects")

        if start_date.year < 1900 or start_date.year > 2099:
            messages.error(request, "Project start date must be between 1900 and 2099.")
            return redirect("projects")

        if end_date and (end_date.year < 1900 or end_date.year > 2099):
            messages.error(request, "Project end date must be between 1900 and 2099.")
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
    """Display the admin management view for a single project.

    Shows all roles, invites, and project-scoped approval documents. Provides
    buttons to add roles, invite users, upload documents, and view submissions.

    Args:
        pk (int): Primary key of the Project to display.

    Context:
        project (Project): The project with roles, invites, and approval_documents
            prefetched.
        forms (QuerySet[Form]): Active forms available to assign as required forms.
        users (QuerySet[CustomUser]): All users available to invite.
        project_documents (QuerySet[ApprovalDocument]): Project-scoped documents.

    Template: project_detail.html
    """
    if not _is_admin_or_manager(request.user):
        messages.error(request, "You do not have permission to manage projects.")
        return redirect("dashboard")

    project = get_object_or_404(
        Project.objects.prefetch_related(
            Prefetch("roles", queryset=ProjectRole.objects.select_related("required_form")),
            Prefetch("invites", queryset=ProjectInvite.objects.select_related("user", "project_role", "project_role__required_form")),
            "approval_documents",
        ),
        pk=pk,
    )

    forms = Form.objects.filter(is_active=True).order_by("title")
    users = CustomUser.objects.all().order_by("first_name", "last_name", "email")

    project_documents = project.approval_documents.filter(scope="project", is_active=True)

    return render(
        request,
        "project_detail.html",
        {
            "project": project,
            "forms": forms,
            "users": users,
            "project_documents": project_documents,
        },
    )


@login_required
@require_POST
def add_project_role(request, pk):
    """Add a new role to a project, or update its required form if it already exists.

    Uses get_or_create so that re-submitting an existing role title is
    idempotent rather than raising an error.

    Args:
        pk (int): Primary key of the Project to add the role to.

    Returns:
        HttpResponse: Redirect to the project detail page.
    """
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
    """Change or remove the required form assigned to a project role.

    Args:
        project_pk (int): Primary key of the parent Project.
        role_pk (int): Primary key of the ProjectRole to update.

    Returns:
        HttpResponse: Redirect to the project detail page.
    """
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
    """Invite one or more users to a project role and assign the required form.

    For each selected user, creates a new ProjectInvite or resets an existing
    one back to "pending" (unless it is already completed). Also ensures a
    FormAssignment exists if the role has a required form. All database writes
    are wrapped in a single transaction.

    Args:
        project_pk (int): Primary key of the parent Project.
        role_pk (int): Primary key of the ProjectRole to invite users into.

    Returns:
        HttpResponse: Redirect to the project detail page with a summary message.
    """
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
@require_POST
def add_project_approval_document(request, pk):
    """Upload a project-scoped approval document (PDF only).

    Args:
        pk (int): Primary key of the Project to attach the document to.

    Returns:
        HttpResponse: Redirect to the project detail page.
    """
    if not _is_admin_or_manager(request.user):
        return HttpResponseForbidden("Permission denied")

    project = get_object_or_404(Project, pk=pk)
    title = (request.POST.get("title") or "").strip()
    uploaded_file = request.FILES.get("document")

    if not title or not uploaded_file:
        messages.error(request, "Document title and file are required.")
        return redirect("project_detail", pk=project.pk)

    if not uploaded_file.name.lower().endswith(".pdf"):
        messages.error(request, "Only PDF files are supported.")
        return redirect("project_detail", pk=project.pk)

    ApprovalDocument.objects.create(
        project=project,
        scope="project",
        title=title,
        document=uploaded_file,
        uploaded_by=request.user,
    )

    messages.success(request, "Project approval document added.")
    return redirect("project_detail", pk=project.pk)


@login_required
@require_POST
def add_role_approval_document(request, project_pk, role_pk):
    """Upload a role-scoped approval document (PDF only) for a specific project role.

    Args:
        project_pk (int): Primary key of the parent Project.
        role_pk (int): Primary key of the ProjectRole to attach the document to.

    Returns:
        HttpResponse: Redirect to the project detail page.
    """
    if not _is_admin_or_manager(request.user):
        return HttpResponseForbidden("Permission denied")

    role = get_object_or_404(ProjectRole, pk=role_pk, project_id=project_pk)
    title = (request.POST.get("title") or "").strip()
    uploaded_file = request.FILES.get("document")

    if not title or not uploaded_file:
        messages.error(request, "Document title and file are required.")
        return redirect("project_detail", pk=project_pk)

    if not uploaded_file.name.lower().endswith(".pdf"):
        messages.error(request, "Only PDF files are supported.")
        return redirect("project_detail", pk=project_pk)

    ApprovalDocument.objects.create(
        project=role.project,
        role=role,
        scope="role",
        title=title,
        document=uploaded_file,
        uploaded_by=request.user,
    )

    messages.success(request, f'Approval document added for role "{role.title}".')
    return redirect("project_detail", pk=project_pk)


@login_required
@require_POST
def delete_approval_document(request, doc_id):
    """Permanently delete an approval document.

    Args:
        doc_id (int): Primary key of the ApprovalDocument to delete.

    Returns:
        HttpResponse: Redirect to the document's parent project detail page.
    """
    if not _is_admin_or_manager(request.user):
        return HttpResponseForbidden("Permission denied")

    document = get_object_or_404(ApprovalDocument, pk=doc_id)
    project_id = document.project_id
    document.delete()

    messages.success(request, "Approval document deleted.")
    return redirect("project_detail", pk=project_id)

@login_required
def my_projects(request):
    """Show the current user's project invites with their submission and approval status.

    For approved invites, approval documents relevant to the worker are also
    fetched and included so the worker can download them from this page.

    Context:
        invite_rows (list[dict]): Each entry contains the invite and a list of
            relevant ApprovalDocuments (empty unless review_status is "approved").

    Template: my_projects.html
    """
    invites = (
        ProjectInvite.objects
        .filter(user=request.user)
        .select_related("project", "project_role", "project_role__required_form")
        .order_by("-invited_at")
    )

    invite_rows = []
    for invite in invites:
        invite_rows.append({
            "invite": invite,
            "approval_documents": _get_invite_approval_documents(invite) if invite.review_status == "approved" else [],
        })

    return render(request, "my_projects.html", {"invite_rows": invite_rows})


@login_required
def project_invite_form(request, invite_id):
    """Allow a worker to fill in and submit the required form for a project invite.

    On first visit marks the invite as "viewed". On POST, validates all required
    questions, creates a FormSubmission with Answer records, marks the invite as
    "completed", and updates the FormAssignment. The view also loads any saved
    draft answers to pre-populate the form.

    For licence_upload questions, if no file is uploaded the view attempts to
    use the worker's existing credential image for that licence type.

    Args:
        invite_id (int): Primary key of the ProjectInvite. Only the invited user
            may access this view (enforced by user=request.user in get_object_or_404).

    Context:
        invite, form_obj, questions (with draft_value and prefilled_licence attrs
        injected), draft_answers.

    Template: project_invite_form.html
    """
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
                elif q.question_type in ["file", "licence_upload"]:
                    answer_value = q.options_text if q.question_type == "licence_upload" else ""
                    if q.question_type == "licence_upload" and not uploaded_file:
                        existing_licence = request.user.credentials.filter(title=q.options_text, image__isnull=False).first()
                        if existing_licence:
                            uploaded_file = existing_licence.image
                else:
                    answer_value = request.POST.get(key, "")

                if q.is_required:
                    if q.question_type in ["file", "licence_upload"] and not uploaded_file:
                        messages.error(request, f'Question "{q.question_text}" is required.')
                        submission.delete()
                        return redirect("project_invite_form", invite_id=invite.id)
                    if q.question_type not in ["file", "licence_upload"] and not answer_value:
                        messages.error(request, f'Question "{q.question_text}" is required.')
                        submission.delete()
                        return redirect("project_invite_form", invite_id=invite.id)

                Answer.objects.create(
                    submission=submission,
                    question=q,
                    answer_text=answer_value or "",
                    answer_file=uploaded_file if uploaded_file else None,
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
                                                                              
    draft = FormDraft.objects.filter(user=request.user, invite=invite).first()
    draft_answers = draft.answers_json if draft else {}
    
    for q in questions:
        q.draft_value = draft_answers.get(f"question_{q.id}", "")
        if q.question_type == 'licence_upload':                                                             
            q.prefilled_licence = request.user.credentials.filter(title=q.options_text, image__isnull=False).first()
    
                                                                                                            
    return render(  
        request,
        "project_invite_form.html",
        {                                                                                                   
            "invite": invite,
            "form_obj": required_form,                                                                      
            "questions": questions,
            "draft_answers": draft_answers                                                
        },
    ) 
    
@login_required
@require_POST
def save_form_draft(request, invite_id):
    """Persist a single question's answer to the FormDraft for the given invite.

    Called by HTMX on each field change to auto-save progress. Stores the
    answer under the key "question_<id>" in the draft's answers_json dict.

    Args:
        invite_id (int): Primary key of the ProjectInvite being drafted.

    Returns:
        HttpResponse: 204 No Content on success, 400 if question_id is missing.
    """
    invite = get_object_or_404(
        ProjectInvite,
        pk=invite_id,
        user=request.user,
    )
    
    question_id = request.POST.get("question_id")
    value = request.POST.getlist("value")
    
    if not question_id:
        return HttpResponse(status=400)
    
    if len(value) == 1:
        value = value[0]
        
    draft, _ = FormDraft.objects.get_or_create(
        user=request.user,
        invite=invite,
    )
    
    draft.answers_json[question_id] = value
    draft.save(update_fields=["answers_json", "updated_at"])
    
    return HttpResponse(status=204)

@login_required
def start_induction(request):
    """Create a new inactive user and send them an account setup email.

    The new user is created with is_active=False and an unusable password.
    An OnboardingInvite with a secure random token is created, and a setup
    link is emailed to the provided address. The worker activates their account
    by following the link and setting a password.

    Restricted to admin and manager roles.

    Returns:
        HttpResponse: Redirect to the personnel list in all cases (GET or POST).
    """
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
        # print("EMAIL_BACKEND =", settings.EMAIL_BACKEND)
        
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
    """Render and process the default onboarding data-capture form.

    Locks the identity fields (email, first_name, last_name) to the invited
    user so they cannot be overridden by form data. On POST, calls
    create_or_update_user_from_post to upsert the user's profile and credentials,
    then marks the invite as completed.

    Any OCR data stored in the session from the licence_scan step is popped and
    passed to the template to pre-fill date of birth and licence number fields.

    Args:
        token (str): The unique token from the OnboardingInvite.

    Context:
        invite, user_obj, ocr_dob (str), ocr_licence_number (str).

    Template: forms/onboarding_default_form.html
    """
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

@login_required
def project_submissions(request, pk):
    """Display all invite/submission rows for a project, grouped by role.

    For each role, fetches the latest FormSubmission for each invited user and
    computes their derived status and compliance state. Used by admins to review
    and approve or reject member submissions.

    Args:
        pk (int): Primary key of the Project to view submissions for.

    Context:
        project (Project): The project with roles and invites prefetched.
        role_sections (list[dict]): Each entry has a "role" (ProjectRole) and
            "rows" (list of dicts with invite, user, submission, derived_status,
            has_compliance_issue, expired_credentials).

    Template: project_submissions.html
    """
    if not _is_admin_or_manager(request.user):
        messages.error(request, "You do not have permission to view project submissions.")
        return redirect("dashboard")

    project = get_object_or_404(
        Project.objects.prefetch_related(
            Prefetch(
                "roles",
                queryset=ProjectRole.objects.select_related("required_form")
            ),
            Prefetch(
                "invites",
                queryset=ProjectInvite.objects.select_related(
                    "user",
                    "project_role",
                    "project_role__required_form",
                    "reviewed_by",
                ).prefetch_related("user__credentials")
            ),
        ),
        pk=pk,
    )

    role_sections = []

    for role in project.roles.all().order_by("title"):
        role_invites = [invite for invite in project.invites.all() if invite.project_role_id == role.id]
        rows = []

        for invite in role_invites:
            required_form = role.required_form
            latest_submission = None

            if required_form:
                latest_submission = (
                    FormSubmission.objects
                    .filter(form=required_form, user=invite.user)
                    .order_by("-submitted_at")
                    .first()
                )

            derived_status, has_issue, expired_creds = _project_member_status(invite)

            rows.append({
                "invite": invite,
                "user": invite.user,
                "submission": latest_submission,
                "derived_status": derived_status,
                "has_compliance_issue": has_issue,
                "expired_credentials": expired_creds,
            })

        role_sections.append({
            "role": role,
            "rows": rows,
        })

    return render(
        request,
        "project_submissions.html",
        {
            "project": project,
            "role_sections": role_sections,
        },
    )


@login_required
def view_submission(request, submission_id):
    """Display the answers for a single FormSubmission and its review state.

    Also resolves the linked ProjectInvite so the template can show the review
    status and provide approve/reject controls.

    Args:
        submission_id (int): Primary key of the FormSubmission to display.

    Context:
        submission (FormSubmission): The submission with form, user, answers,
            and attached_credentials prefetched.
        answers (QuerySet[Answer]): Answers ordered by question display order.
        linked_invite (ProjectInvite | None): The most recent invite linking this
            user to a role that requires this form, or None if not found.

    Template: submission_detail.html
    """
    if not _is_admin_or_manager(request.user):
        messages.error(request, "You do not have permission to view submissions.")
        return redirect("dashboard")

    submission = get_object_or_404(
        FormSubmission.objects.select_related("form", "user").prefetch_related(
            "answers__question",
            "attached_credentials",
        ),
        pk=submission_id,
    )

    linked_invite = (
        ProjectInvite.objects.select_related(
            "project",
            "project_role",
            "project_role__required_form",
            "reviewed_by",
        )
        .filter(user=submission.user, project_role__required_form=submission.form)
        .order_by("-invited_at")
        .first()
    )

    answers = submission.answers.all().order_by("question__order")

    return render(
        request,
        "submission_detail.html",
        {
            "submission": submission,
            "answers": answers,
            "linked_invite": linked_invite,
        },
    )
    
@login_required
@require_POST
def delete_project(request, pk):
    """Permanently delete a project and all related data (cascade).

    Args:
        pk (int): Primary key of the Project to delete.

    Returns:
        HttpResponse: Redirect to the projects list with a success message.
    """
    if not _is_admin_or_manager(request.user):
        return HttpResponseForbidden("Permission Denied")

    project = get_object_or_404(Project, pk=pk)
    project_title = project.title
    project.delete()
    
    messages.success(request, f'Project "{project_title}" has been deleted.')
    return redirect("projects")