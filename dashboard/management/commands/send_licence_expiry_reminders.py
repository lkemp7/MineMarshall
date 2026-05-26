from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings

from dashboard.models import Credential, CredentialNotification
from dashboard.services import (
    get_eligible_licence_reminder_band,
    create_licence_renewal_request,
    build_licence_renewal_url,
)


class Command(BaseCommand):
    """Management command to send driver's licence expiry reminder emails.

    Iterates over all Credential records and uses the service layer to determine
    whether a reminder is due. Creates a LicenceRenewalRequest (with a unique
    token) and emails the worker a secure renewal link. Records a
    CredentialNotification so that duplicate emails are not sent within the
    same reminder band.

    Run on a schedule (e.g. daily cron) via:
        python manage.py send_licence_expiry_reminders

    Use --dry-run to preview which emails would be sent without side effects.
    """

    help = "Scan Driver Licence credentials and send expiry reminder emails."

    def add_arguments(self, parser):
        """Register the optional --dry-run flag."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show which reminders would be sent without creating records or sending email.",
        )

    def handle(self, *args, **options):
        """Main entry point: iterate credentials, check eligibility, send emails.

        Args:
            *args: Unused positional arguments passed by Django.
            **options: Parsed command-line options (dry_run: bool).
        """
        dry_run = options["dry_run"]

        credentials = Credential.objects.select_related("user").all()
        reminders_sent = 0

        for credential in credentials:
            # get_eligible_licence_reminder_band returns None if no reminder is due
            reminder_band = get_eligible_licence_reminder_band(credential)
            if not reminder_band:
                continue

            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f"DRY RUN: would send {reminder_band} reminder to "
                        f"{credential.user.email} for credential #{credential.id}"
                    )
                )
                continue

            # Create the renewal request with a secure token for the email link
            renewal_request = create_licence_renewal_request(credential, reminder_band)
            renewal_url = build_licence_renewal_url(renewal_request)

            subject = f"MineMarshall licence expiry reminder - {reminder_band.replace('_', ' ')}"
            message = (
                f"Hello {credential.user.first_name or credential.user.email},\n\n"
                f"Your Driver Licence is in the '{reminder_band.replace('_', ' ')}' reminder period.\n\n"
                f"Please use the secure link below to upload your renewed licence:\n"
                f"{renewal_url}\n\n"
                f"After upload, the system will OCR-scan the licence and show you the extracted details "
                f"for confirmation before your record is updated.\n\n"
                f"If you were not expecting this email, please contact your administrator.\n\n"
                f"Regards,\n"
                f"MineMarshall"
            )

            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[credential.user.email],
                fail_silently=False,
            )

            # Record that this band has been notified to prevent duplicate sends
            CredentialNotification.objects.create(
                credential=credential,
                reminder_band=reminder_band,
            )

            reminders_sent += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"Sent {reminder_band} reminder to {credential.user.email}"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(f"Done. Reminders sent: {reminders_sent}")
        )