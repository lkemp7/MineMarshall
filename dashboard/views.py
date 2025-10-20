from django.contrib.auth.decorators import login_required
from accounts.models import CustomUser
from .models import Form, Question
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from .services import create_or_update_user_from_post
from dashboard.models import Credential
from django.utils import timezone
from django.contrib import messages

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
    return render(request, "form_detail.html", {"form": form_obj})


@login_required
def personnel(request):
    users = CustomUser.objects.all().order_by("first_name", "last_name")
    return render(request, 'personnel.html', {"users": users})


@login_required
def user_profile(request, user_id):
    user_qs = CustomUser.objects.prefetch_related("credentials").select_related("worker_profile")
    user_obj = get_object_or_404(user_qs, pk=user_id)
    return render(request, "user_profile.html", {"user_obj": user_obj})

@login_required
def metrics(request):
    return render(request, "metrics.html")

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
def edit_user_profile(request, pk):
    # Check if user has permission
    if request.user.role not in ['admin', 'manager']:
        messages.error(request, 'You do not have permission to edit profiles.')
        return redirect('personnel')
    
    user_obj = get_object_or_404(CustomUser, pk=pk)
    
    if request.method == 'POST':
        # Update basic user info
        user_obj.first_name = request.POST.get('first_name')
        user_obj.last_name = request.POST.get('last_name')
        user_obj.email = request.POST.get('email')
        user_obj.phone_number = request.POST.get('phone_number')
        user_obj.save()
        
        # Update or create worker profile
        if hasattr(user_obj, 'worker_profile'):
            profile = user_obj.worker_profile
        else:
            from dashboard.models import WorkerProfile  # Adjust import as needed
            profile = WorkerProfile.objects.create(user=user_obj)
        
        profile.dob = request.POST.get('dob') or None
        profile.role = request.POST.get('worker_role')
        profile.project = request.POST.get('project')
        profile.employer = request.POST.get('employer')
        profile.emergency_contact_name = request.POST.get('emergency_contact_name')
        profile.emergency_contact_mobile = request.POST.get('emergency_contact_mobile')
        profile.save()
        
        messages.success(request, f'Profile updated for {user_obj.first_name} {user_obj.last_name}')
        return redirect('user_profile', pk=pk)
    
    return redirect('user_profile', pk=pk)