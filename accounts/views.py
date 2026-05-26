
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
    """Allow the logged-in user to update their own profile information.

    GET  - renders the profile edit form pre-populated with the current user's data.
    POST - validates and saves the form, then redirects back to the account page.

    Context:
        form (UserProfileForm): The bound or unbound profile form.

    Template: accounts/userAccount.html
    """
    user = request.user
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect('account')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = UserProfileForm(instance=user)

    return render(request, 'accounts/userAccount.html', {'form': form})


@login_required
def redirect_user(request):
    """Redirect an authenticated user straight to the dashboard.

    Used as the post-login landing point for users who have already completed
    account setup.
    """
    return redirect('dashboard')


def setup_account(request, token):
    """Allow a new user to set their password via an onboarding invite link.

    The token is stored on an OnboardingInvite and emailed during induction.
    On success the user is activated, logged in, and routed either to the
    licence scan step (if required) or directly to the dashboard.

    Args:
        token (str): The unique token from the OnboardingInvite.

    Context:
        invite (OnboardingInvite): The invite record for the token.

    Template: accounts/setup_account.html
    """
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

        # Advance invite status depending on whether a default form is required
        if invite.requires_default_form:
            invite.status = "default_form_pending"
        else:
            invite.status = "account_created"
        invite.save()

        # Clear any queued messages before logging the user in to avoid stale alerts
        list(messages.get_messages(request))
        login(request, user)

        if invite.requires_default_form:
            return redirect('licence_scan', token=invite.token)

        return redirect('dashboard')

    return render(request, "accounts/setup_account.html", {"invite": invite})


@login_required
def licence_scan(request, token):
    """Optional step during onboarding: scan a driver's licence with OCR.

    If an image is uploaded, easyOCR + Ollama extract the licence fields and
    store them in the session for the default form to pre-populate. A
    Credential record is also created or updated for the user. The step can
    be skipped by submitting without a file.

    Args:
        token (str): The unique token from the OnboardingInvite.

    Context:
        invite (OnboardingInvite): The current onboarding invite.

    Template: accounts/licence_scan.html
    """
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

            # Persist OCR results in session so the default form can pre-fill them
            request.session[f"licence_ocr_{token}"] = ocr_data

            Credential.objects.update_or_create(
                user=invite.user,
                title=ocr_data["title"],
                defaults={
                    "licence_number": ocr_data["licence_number"],
                    "expiry_date": ocr_data["expiry"],
                    "image": ContentFile(image_bytes, name=image_file.name),
                    "required": False,
                },
            )

        return redirect('onboarding_default_form', token=token)

    return render(request, "accounts/licence_scan.html", {"invite": invite})


def licence_renewal_upload(request, token):
    """Step 1 of the licence renewal flow: upload a new licence image.

    Accessed via the tokenised link sent by the scheduled reminder email.
    Rejects already-used tokens to prevent duplicate renewals. On successful
    upload, OCR extracts the new details and the user is forwarded to the
    confirmation step.

    Args:
        token (str): The unique token from the LicenceRenewalRequest.

    Context:
        renewal_request (LicenceRenewalRequest): The renewal record for the token.

    Template: accounts/licence_renewal_upload.html
    """
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
        # Seek back to the beginning so the file can be saved to the model
        image.seek(0)

        # Store extracted OCR data in session for the confirmation step
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
    """Step 2 of the licence renewal flow: review OCR data and confirm or re-upload.

    Reads the OCR results stored in the session by licence_renewal_upload. The
    user can either confirm (writing the new details to the Credential) or go
    back and re-upload a clearer image. Marks the renewal request as used on
    confirmation so the token cannot be reused.

    Args:
        token (str): The unique token from the LicenceRenewalRequest.

    Context:
        renewal_request (LicenceRenewalRequest): The renewal record.
        credential (Credential): The credential being renewed.
        ocr_data (dict): Extracted licence fields from the session.

    Template: accounts/licence_renewal_confirm.html
    """
    renewal_request = get_object_or_404(
        LicenceRenewalRequest.objects.select_related("credential", "user"),
        token=token,
    )

    if renewal_request.is_used:
        return render(request, "accounts/licence_renewal_invalid.html")

    session_key = f"licence_renewal_ocr_{token}"
    ocr_data = request.session.get(session_key)

    if not ocr_data:
        # No session data means the user skipped step 1 — send them back
        return redirect("licence_renewal_upload", token=token)

    credential = renewal_request.credential

    if request.method == "POST":
        if "reupload" in request.POST:
            # Clear session and delete the staged image so the user can start over
            request.session.pop(session_key, None)

            if renewal_request.renewal_image:
                renewal_request.renewal_image.delete(save=False)
                renewal_request.renewal_image = None
                renewal_request.save(update_fields=["renewal_image"])

            return redirect("licence_renewal_upload", token=token)

        if "confirm" in request.POST:
            # Apply the new image to the existing credential record
            if renewal_request.renewal_image:
                credential.image = renewal_request.renewal_image

            # Only overwrite licence_number if OCR returned a value
            credential.licence_number = ocr_data.get("licence_number") or credential.licence_number

            expiry_value = ocr_data.get("expiry")
            if expiry_value:
                try:
                    credential.expiry_date = datetime.strptime(expiry_value, "%Y-%m-%d").date()
                except ValueError:
                    pass

            credential.save()

            # Mark the token as used to prevent re-use
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
    """Final step of the licence renewal flow: display the success confirmation page.

    Args:
        token (str): The unique token from the LicenceRenewalRequest.

    Context:
        renewal_request (LicenceRenewalRequest): The completed renewal record.

    Template: accounts/licence_renewal_success.html
    """
    renewal_request = get_object_or_404(LicenceRenewalRequest, token=token)
    return render(
        request,
        "accounts/licence_renewal_success.html",
        {"renewal_request": renewal_request},
    )
