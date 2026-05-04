
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import UserProfileForm
from django.shortcuts import get_object_or_404
from django.contrib.auth import login
from dashboard.models import OnboardingInvite, Credential
from django.core.files.base import ContentFile
from .ocr import extract_licence_fields
from django.utils import timezone
from dashboard.models import LicenceRenewalRequest
from datetime import datetime

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

        list(messages.get_messages(request))
        login(request, user)

        if invite.requires_default_form:
            return redirect('licence_scan', token=invite.token)

        return redirect('dashboard')

    return render(request, "accounts/setup_account.html", {"invite": invite})


@login_required
def licence_scan(request, token):
    invite = get_object_or_404(OnboardingInvite, token=token)

    if request.method == "POST":
        image_file = request.FILES.get("licence_image")

        if image_file:
            image_bytes = image_file.read()
            ocr_data = extract_licence_fields(image_bytes)

            if not any(ocr_data.get(k) for k in ("first_name", "last_name", "dob", "licence_number", "expiry")):
                messages.error(
                    request,
                    "Could not read the licence. Please check the image and try again, or skip this step."
                )
                return render(request, "accounts/licence_scan.html", {"invite": invite})

            request.session[f"licence_ocr_{token}"] = ocr_data
            
            Credential.objects.update_or_create(
                user = invite.user,
                title = ocr_data["title"],
                defaults = {
                    "licence_number": ocr_data["licence_number"],
                    "expiry_date": ocr_data["expiry"],
                    "image": ContentFile(image_bytes, name = image_file.name), 
                    "required": False,
                },
            )

        return redirect('onboarding_default_form', token=token)

    return render(request, "accounts/licence_scan.html", {"invite": invite})


def licence_renewal_upload(request, token):
    renewal_request = get_object_or_404(
        LicenceRenewalRequest.objects.select_related("credential", "user"),
        token=token,
    )

    if renewal_request.is_used:
        return render(request, "accounts/licence_renewal_invalid.html")

    session_key = f"licence_renewal_ocr_{token}"

    if request.method == "POST" and request.FILES.get("licence_image"):
        image = request.FILES["licence_image"]
        extracted = extract_licence_fields(image.read())
        image.seek(0)

        request.session[session_key] = {
            "licence_number": extracted.get("licence_number", ""),
            "expiry": extracted.get("expiry", ""),
        }

        renewal_request.renewal_image = image
        renewal_request.save(update_fields=["renewal_image"])

        return redirect("licence_renewal_confirm", token=token)

    return render(
        request,
        "accounts/licence_renewal_upload.html",
        {"renewal_request": renewal_request},
    )

def licence_renewal_confirm(request, token):
    renewal_request = get_object_or_404(
        LicenceRenewalRequest.objects.select_related("credential", "user"),
        token=token,
    )

    if renewal_request.is_used:
        return render(request, "accounts/licence_renewal_invalid.html")

    session_key = f"licence_renewal_ocr_{token}"
    ocr_data = request.session.get(session_key)

    if not ocr_data:
        return redirect("licence_renewal_upload", token=token)

    credential = renewal_request.credential

    if request.method == "POST":
        if "reupload" in request.POST:
            request.session.pop(session_key, None)

            if renewal_request.renewal_image:
                renewal_request.renewal_image.delete(save=False)
                renewal_request.renewal_image = None
                renewal_request.save(update_fields=["renewal_image"])

            return redirect("licence_renewal_upload", token=token)

        if "confirm" in request.POST:
            if renewal_request.renewal_image:
                credential.image = renewal_request.renewal_image

            credential.licence_number = ocr_data.get("licence_number") or credential.licence_number

            expiry_value = ocr_data.get("expiry")
            if expiry_value:
                try:
                    credential.expiry_date = datetime.strptime(expiry_value, "%Y-%m-%d").date()
                except ValueError:
                    pass

            credential.save()

            renewal_request.is_used = True
            renewal_request.completed_at = timezone.now()
            renewal_request.save(update_fields=["is_used", "completed_at"])

            request.session.pop(session_key, None)

            return redirect("licence_renewal_success", token=token)

    context = {
        "renewal_request": renewal_request,
        "credential": credential,
        "ocr_data": ocr_data,
    }
    return render(request, "accounts/licence_renewal_confirm.html", context)

def licence_renewal_success(request, token):
    renewal_request = get_object_or_404(LicenceRenewalRequest, token=token)
    return render(
        request,
        "accounts/licence_renewal_success.html",
        {"renewal_request": renewal_request},
    )
