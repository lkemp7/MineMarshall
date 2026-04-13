from datetime import datetime
from django.contrib.auth import get_user_model
from .models import WorkerProfile
from .models import Credential


User = get_user_model()

def create_or_update_user_from_post(data):
    """
    Accepts request.POST (a QueryDict). Creates/updates:
      - CustomUser (by email)
      - WorkerProfile (extra fields)
      - Credential rows (required + optional)
    Returns the user instance or None if no email provided.
    """

    # ---- Personal details (4x5 table) ----
    first_name = (data.get("first_name") or "").strip()
    last_name  = (data.get("last_name") or "").strip()
    email      = (data.get("email") or "").strip().lower()
    mobile     = (data.get("mobile") or "").strip()
    dob        = (data.get("dob") or "").strip()

    role       = (data.get("role") or "").strip()
    project    = (data.get("project") or "").strip()
    employer   = (data.get("employer") or "").strip()
    ec_name    = (data.get("emergency_contact_name") or "").strip()
    ec_mobile  = (data.get("emergency_contact_mobile") or "").strip()

    if not email:
        return None

    # ---- User create/update ----
    user, created = User.objects.get_or_create(
        email=email,
        defaults={"first_name": first_name, "last_name": last_name, "phone_number": mobile}
    )
    if not created:
        changed = False
        if first_name and user.first_name != first_name:
            user.first_name = first_name; changed = True
        if last_name and user.last_name != last_name:
            user.last_name = last_name; changed = True
        # adjust if your CustomUser uses a different phone field name
        if mobile and getattr(user, "phone_number", "") != mobile:
            user.phone_number = mobile; changed = True
        if changed:
            user.save()

    # ---- Profile create/update ----
    profile, _ = WorkerProfile.objects.get_or_create(user=user)
    if dob:
        try:
            profile.dob = datetime.strptime(dob, "%Y-%m-%d").date()
        except ValueError:
            pass
    profile.role = role
    profile.project = project
    profile.employer = employer
    profile.emergency_contact_name = ec_name
    profile.emergency_contact_mobile = ec_mobile
    profile.save()

    # ---- Helper to save a required credential row ----
    def _save_req(title, issue_key, expiry_key):
        issue_s  = (data.get(issue_key) or "").strip()
        expiry_s = (data.get(expiry_key) or "").strip()
        issue_d = expiry_d = None
        try:
            if issue_s:  issue_d  = datetime.strptime(issue_s,  "%Y-%m-%d").date()
            if expiry_s: expiry_d = datetime.strptime(expiry_s, "%Y-%m-%d").date()
        except ValueError:
            # ignore bad dates silently for now
            pass

        Credential.objects.update_or_create(
            user=user, title=title, required=True,
            defaults={"issue_date": issue_d, "expiry_date": expiry_d},
        )

    # ---- Required credentials (3 fixed rows) ----
    _save_req("Site Induction", "req_site_induction_issue", "req_site_induction_expiry")
    _save_req("Medical",        "req_medical_issue",        "req_medical_expiry")
    _save_req("Photo ID",       "req_photo_id_issue",       "req_photo_id_expiry")

    licence_number = (data.get("driver_licence_number") or "").strip()
    if licence_number:
        Credential.objects.update_or_create(
            user=user, title="Driver Licence",
            defaults={"licence_number": licence_number, "required": False},
        )

    # ---- Optional credentials (variable rows) ----
    # data should be a QueryDict so getlist() works. If you ever pass a plain dict,
    # wrap with: from django.http import QueryDict
    titles   = data.getlist("opt_title[]")
    issues   = data.getlist("opt_issue[]")
    expiries = data.getlist("opt_expiry[]")

    for i, t in enumerate(titles):
        title = (t or "").strip()
        if not title:
            continue
        issue_s  = issues[i]   if i < len(issues)   else ""
        expiry_s = expiries[i] if i < len(expiries) else ""
        issue_d = expiry_d = None
        try:
            if issue_s:  issue_d  = datetime.strptime(issue_s,  "%Y-%m-%d").date()
            if expiry_s: expiry_d = datetime.strptime(expiry_s, "%Y-%m-%d").date()
        except ValueError:
            pass

        # If you want idempotency per-title, use update_or_create instead of create
        Credential.objects.create(
            user=user, title=title, issue_date=issue_d, expiry_date=expiry_d, required=False
        )

    return user