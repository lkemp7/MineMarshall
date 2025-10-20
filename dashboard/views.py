from django.contrib.auth.decorators import login_required
from accounts.models import CustomUser
from django.contrib import messages
from .models import Form, Question
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from .services import create_or_update_user_from_post
from dashboard.models import WorkerProfile, Credential
from django.utils import timezone

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
            return redirect('user_profile', pk=user.pk)
            
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
        return redirect('user_profile', pk=pk)
    
    return redirect('user_profile', pk=pk)

@login_required
def save_credential(request, pk):
    if request.user.role not in ['admin', 'manager']:
        messages.error(request, 'You do not have permission to edit credentials.')
        return redirect('personnel')
    
    user_obj = get_object_or_404(CustomUser, pk=pk)
    
    if request.method == 'POST':
        credential_id = request.POST.get('credential_id')
        
        if credential_id:
            # Edit existing credential
            credential = get_object_or_404(Credential, id=credential_id, user=user_obj)
        else:
            # Create new credential
            credential = Credential(user=user_obj)
        
        credential.title = request.POST.get('title')
        issue_date = request.POST.get('issue_date')
        credential.issue_date = issue_date if issue_date else None
        expiry_date = request.POST.get('expiry_date')
        credential.expiry_date = expiry_date if expiry_date else None
        credential.required = request.POST.get('required') == 'on'
        credential.save()
        
        messages.success(request, 'Credential saved successfully')
        return redirect('user_profile', pk=pk)
    
    return redirect('user_profile', pk=pk)

@login_required
def delete_user(request, pk):
    if request.user.role not in ['admin', 'manager']:
        messages.error(request, 'You do not have permission to delete users.')
        return redirect('personnel')
    
    user_obj = get_object_or_404(CustomUser, pk=pk)
    
    # Prevent users from deleting themselves
    if user_obj.pk == request.user.pk:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('user_profile', pk=pk)
    
    # Prevent managers from deleting admins
    if request.user.role == 'manager' and user_obj.role == 'admin':
        messages.error(request, 'Managers cannot delete admin users.')
        return redirect('user_profile', pk=pk)
    
    if request.method == 'POST':
        user_name = f"{user_obj.first_name} {user_obj.last_name}"
        user_obj.delete()
        messages.success(request, f'User {user_name} has been deleted.')
        return redirect('personnel')
    
    return redirect('user_profile', pk=pk)