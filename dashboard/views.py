from django.contrib.auth.decorators import login_required
from accounts.models import CustomUser
from django.contrib import messages
from .models import Form, Question
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from .services import create_or_update_user_from_post
from dashboard.models import WorkerProfile, Credential
from django.utils import timezone
from django.contrib import messages
from django.template.loader import render_to_string
import uuid

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
        return redirect('user_profile', user_id=pk)
    
    return redirect('user_profile', user_id=pk)

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

@login_required
def create_form(request):
    if request.user.role not in ['admin', 'manager']:
        messages.error(request, 'You do not have permission to create forms.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        title = request.POST.get('title', 'Untitled Form')
        description = request.POST.get('description', '')
        
        # Create the form
        form = Form.objects.create(
            title=title,
            description=description,
            created_by=request.user
        )
        
        # Get number of questions
        num_questions = int(request.POST.get('num_questions', 0))
        
        # Create questions
        for i in range(1, num_questions + 1):
            question_text = request.POST.get(f'question_{i}')
            question_type = request.POST.get(f'question_type_{i}', 'text')
            options = request.POST.get(f'options_{i}', '')
            is_required = request.POST.get(f'required_{i}') == 'on'
            
            if question_text:
                Question.objects.create(
                    form=form,
                    question_text=question_text,
                    question_type=question_type,
                    options_text=options if question_type in ['radio', 'checkbox', 'dropdown'] else '',
                    is_required=is_required,
                    order=i
                )
        
        messages.success(request, f'Form "{title}" created successfully!')
        return redirect('view_form', pk=form.pk)
    
    return render(request, 'create_form.html')

@login_required
def add_question_field(request):
    """Returns HTML for a new question field via HTMX"""
    question_id = str(uuid.uuid4())[:8]  # Unique ID for this question
    
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
    </div>
    '''
    return HttpResponse(html)

@login_required
def create_form(request):
    if request.user.role not in ['admin', 'manager']:
        return HttpResponse(status=403)
    
    if request.method == 'POST':
        title = request.POST.get('title', 'Untitled Form')
        description = request.POST.get('description', '')
        
        # Create the form
        form = Form.objects.create(
            title=title,
            description=description,
            created_by=request.user
        )
        
        # Process questions - they come as questions[uuid][field]
        questions_data = {}
        for key, value in request.POST.items():
            if key.startswith('questions['):
                # Parse: questions[uuid][field] -> uuid, field
                parts = key.split('[')
                if len(parts) >= 3:
                    uuid = parts[1].rstrip(']')
                    field = parts[2].rstrip(']')
                    
                    if uuid not in questions_data:
                        questions_data[uuid] = {}
                    questions_data[uuid][field] = value
        
        # Create Question objects
        order = 1
        for uuid, data in questions_data.items():
            if 'text' in data and data['text']:
                Question.objects.create(
                    form=form,
                    question_text=data.get('text', ''),
                    question_type=data.get('type', 'text'),
                    options_text=data.get('options', ''),
                    is_required=data.get('required') == 'on',
                    order=order
                )
                order += 1
        
        # Close modal and refresh page via HTMX
        response = HttpResponse()
        response['HX-Redirect'] = f'/dashboard/forms/{form.pk}/'
        return response
    
    return HttpResponse(status=405)