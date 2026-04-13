
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import UserProfileForm
from django.shortcuts import get_object_or_404
from django.contrib.auth import login
from dashboard.models import OnboardingInvite
from .ocr import extract_license_fields

@login_required
def edit_profile(request):
    user = request.user
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect('account')   # keep the same page or change to another view
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = UserProfileForm(instance=user)

    return render(request, 'accounts/userAccount.html', {'form': form})


@login_required
def redirect_user(request):
    return redirect('dashboard')

def setup_account(request, token):
    invite = get_object_or_404(OnboardingInvite, token=token)

    if request.method == "POST":
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if not password or not confirm_password:
            messages.error(request, "Both password fields are required.")
            return render(request, "accounts/setup_account.html", {"invite": invite})

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "accounts/setup_account.html", {"invite": invite})

        user = invite.user
        user.set_password(password)
        user.is_active = True
        user.save()

        if invite.requires_default_form:
            invite.status = "default_form_pending"
        else:
            invite.status = "account_created"
        invite.save()

        login(request, user)

        if invite.requires_default_form:
            return redirect('license_scan', token=invite.token)

        return redirect('dashboard')

    return render(request, "accounts/setup_account.html", {"invite": invite})


@login_required
def license_scan(request, token):
    invite = get_object_or_404(OnboardingInvite, token=token)

    if request.method == "POST":
        image_file = request.FILES.get("license_image")

        if image_file:
            image_bytes = image_file.read()
            ocr_data = extract_license_fields(image_bytes)

            if all(v is None for v in ocr_data.values()):
                messages.error(
                    request,
                    "Could not read the licence. Please check the image and try again, or skip this step."
                )
                return render(request, "accounts/license_scan.html", {"invite": invite})

            request.session[f"license_ocr_{token}"] = ocr_data

        return redirect('onboarding_default_form', token=token)

    return render(request, "accounts/license_scan.html", {"invite": invite})
