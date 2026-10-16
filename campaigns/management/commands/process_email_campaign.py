import os
import imaplib
from html import escape

from datetime import timedelta
from email.mime.image import MIMEImage

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from campaigns.models import Batch, BatchLead, EmailLog
from campaigns.unsubscribe import (
    get_unsubscribe_url,
    is_email_suppressed,
)


def save_to_sent(msg):
    """
    Save sent email to the IMAP Sent folder.
    This is optional and should not stop the campaign if it fails.
    """
    try:
        imap = imaplib.IMAP4_SSL(
            settings.EMAIL_HOST,
            getattr(settings, "EMAIL_IMAP_PORT", 993)
        )

        imap.login(
            settings.EMAIL_HOST_USER,
            settings.EMAIL_HOST_PASSWORD
        )

        # Try common Sent folder names
        for folder in [
            "Sent",
            "INBOX.Sent",
            "Sent Items",
            "Sent Messages"
        ]:
            result = imap.append(
                folder,
                "\\Seen",
                imaplib.Time2Internaldate(
                    timezone.now().timestamp()
                ),
                msg.message().as_bytes()
            )

            if result[0] == "OK":
                break

        imap.logout()

    except Exception:
        # Do not fail the email campaign if saving to Sent fails
        pass


class Command(BaseCommand):

    help = "Send scheduled campaign emails"

    def handle(self, *args, **kwargs):

        now = timezone.now()

        # Get active batches
        active_batches = Batch.objects.filter(
            status=Batch.Status.ACTIVE
        ).select_related("sequence")

        if not active_batches.exists():
            self.stdout.write(
                self.style.WARNING("No active batches found.")
            )
            return

        for batch in active_batches:

            # Get sequence steps
            steps = list(
                batch.sequence.steps.all().order_by("step_number")
            )

            if not steps:
                self.stdout.write(
                    self.style.WARNING(
                        f"Batch '{batch.name}' has no sequence steps."
                    )
                )
                continue

            # Get leads that still need emails
            batch_leads = batch.batch_leads.filter(
                replied=False,
                unsubscribed=False,
                completed=False
            )

            for batch_lead in batch_leads:

                try:
                    if not batch_lead.email:
                        self.stdout.write(
                            self.style.WARNING(
                                f"SKIP lead {batch_lead.lead_id}: no recipient email is available."
                            )
                        )
                        continue

                    if batch_lead.unsubscribed or is_email_suppressed(
                        batch_lead.email
                    ):
                        if not batch_lead.unsubscribed:
                            batch_lead.unsubscribed = True
                            batch_lead.unsubscribed_at = timezone.now()
                            batch_lead.save(
                                update_fields=["unsubscribed", "unsubscribed_at"]
                            )
                        self.stdout.write(
                            self.style.WARNING(
                                f"SKIP {batch_lead.email} - recipient is unsubscribed"
                            )
                        )
                        continue

                    # current_step starts from 0
                    current_step = batch_lead.current_step

                    # No more steps
                    if current_step >= len(steps):

                        batch_lead.completed = True

                        batch_lead.save(
                            update_fields=["completed"]
                        )

                        continue

                    # Get current sequence step
                    step = steps[current_step]

                    # --------------------------------
                    # CHECK WHEN EMAIL SHOULD BE SENT
                    # --------------------------------

                    if current_step == 0:

                        # Step 0 should only be sent once
                        if batch_lead.last_email_sent_at:

                            self.stdout.write(
                                f"SKIP {batch_lead.email} - "
                                f"Step 0 already sent"
                            )

                            continue

                        send_after = batch.created_at

                    else:

                        # Follow-up requires previous email
                        if not batch_lead.last_email_sent_at:

                            self.stdout.write(
                                f"SKIP {batch_lead.email} - "
                                f"No previous email timestamp"
                            )

                            continue

                        send_after = (
                            batch_lead.last_email_sent_at
                            + timedelta(
                                days=step.delay_days,
                                minutes=step.delay_minutes
                            )
                        )

                    # Not time yet
                    if send_after > now:

                        self.stdout.write(
                            f"SKIP {batch_lead.email} - "
                            f"Step {step.step_number} | "
                            f"send_after={send_after} | "
                            f"now={now}"
                        )

                        continue

                    # --------------------------------
                    # GET TEMPLATE
                    # --------------------------------

                    template = step.template

                    # --------------------------------
                    # LEAD DATA
                    # --------------------------------

                    lead = batch_lead.lead

                    company_name = lead.company.name if lead.company else ""
                    contact_name = lead.contact.name if lead.contact else ""
                    enquiry_for = lead.get_enquiry_for_display()

                    # --------------------------------
                    # REPLACE PLACEHOLDERS
                    # --------------------------------

                    subject = template.subject

                    subject = subject.replace(
                        "{{company_name}}",
                        company_name
                    )

                    subject = subject.replace(
                        "{{name}}",
                        contact_name
                    )

                    subject = subject.replace(
                        "{{First Name}}",
                        contact_name
                    )

                    subject = subject.replace(
                        "{{enquiry_for}}",
                        enquiry_for
                    )

                    body = template.body

                    body = body.replace(
                        "{{company_name}}",
                        company_name
                    )

                    body = body.replace(
                        "{{name}}",
                        contact_name
                    )

                    body = body.replace(
                        "{{First Name}}",
                        contact_name
                    )

                    body = body.replace(
                        "{{enquiry_for}}",
                        enquiry_for
                    )

                    body = body.replace(
                        "{{product_name}}",
                        "Product"
                    )

                    body = body.replace(
                        "{{your_name}}",
                        "sales team"
                    )

                    # Convert normal text line breaks to HTML
                    body = body.replace(
                        "\n",
                        "<br>"
                    )

                    # --------------------------------
                    # ADD SIGNATURE
                    # --------------------------------

                    if template.signature:

                        signature = template.signature.replace(
                            "\n",
                            "<br>"
                        )

                        if template.logo:

                            body += (
                                "<br><br>"
                                "Best Regards,<br>"
                                "<table>"
                                "<tr>"
                                '<td style="vertical-align:middle;'
                                'padding-right:16px;">'
                                '<img src="cid:logo" '
                                'style="max-height:80px;">'
                                "</td>"
                                '<td style="vertical-align:middle;">'
                                f"{signature}"
                                "</td>"
                                "</tr>"
                                "</table>"
                            )

                        else:

                            body += (
                                "<br><br>"
                                "Best Regards,<br>"
                                f"{signature}"
                            )

                    unsubscribe_url = get_unsubscribe_url(batch_lead)
                    body += (
                        '<p style="margin-top:24px;font-size:12px;color:#666;">'
                        "Don't want to receive these emails? "
                        f'<a href="{escape(unsubscribe_url, quote=True)}">'
                        "Unsubscribe</a></p>"
                    )

                    # --------------------------------
                    # CREATE EMAIL
                    # --------------------------------

                    from_email = getattr(
                        settings,
                        "DEFAULT_FROM_EMAIL",
                        settings.EMAIL_HOST_USER
                    )

                    reply_to_email = getattr(
                        settings,
                        "MAILGUN_REPLY_TO",
                        from_email
                    )

                    msg = EmailMultiAlternatives(
                        subject=subject,
                        body=body,
                        from_email=from_email,
                        to=[batch_lead.email],
                        reply_to=[reply_to_email],
                    )
                    msg.content_subtype = "html"
                    msg.extra_headers = {
                        "List-Unsubscribe": f"<{unsubscribe_url}>",
                        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                    }

                    # Needed for inline logo
                    if template.logo:

                        msg.mixed_subtype = "related"

                        with open(
                            template.logo.path,
                            "rb"
                        ) as f:

                            logo_img = MIMEImage(
                                f.read()
                            )

                            logo_img.add_header(
                                "Content-ID",
                                "<logo>"
                            )

                            logo_img.add_header(
                                "Content-Disposition",
                                "inline",
                                filename=os.path.basename(
                                    template.logo.path
                                )
                            )

                            msg.attach(logo_img)

                    # --------------------------------
                    # ATTACHMENT
                    # --------------------------------

                    if template.attachment:

                        with open(
                            template.attachment.path,
                            "rb"
                        ) as f:

                            msg.attach(
                                os.path.basename(
                                    template.attachment.path
                                ),
                                f.read()
                            )

                    # --------------------------------
                    # SEND EMAIL
                    # --------------------------------

                    if is_email_suppressed(batch_lead.email):
                        batch_lead.unsubscribed = True
                        batch_lead.unsubscribed_at = timezone.now()
                        batch_lead.save(
                            update_fields=["unsubscribed", "unsubscribed_at"]
                        )
                        self.stdout.write(
                            self.style.WARNING(
                                f"SKIP {batch_lead.email} - recipient unsubscribed before send"
                            )
                        )
                        continue

                    msg.send()
                    mailgun_message_id = msg.message().get("Message-ID", "")

                    # Save to IMAP Sent
                    save_to_sent(msg)

                    # --------------------------------
                    # CREATE EMAIL LOG
                    # --------------------------------

                    EmailLog.objects.create(
                        batch_lead=batch_lead,
                        template=template,
                        step_number=step.step_number,
                        to_email=batch_lead.email,
                        subject=subject,
                        status=EmailLog.Status.ACCEPTED,
                        mailgun_message_id=mailgun_message_id,
                    )

                    # --------------------------------
                    # UPDATE BATCH LEAD
                    # --------------------------------

                    batch_lead.current_step += 1

                    batch_lead.last_email_sent_at = timezone.now()

                    # Check if sequence is completed
                    if batch_lead.current_step >= len(steps):

                        batch_lead.completed = True

                    batch_lead.save(
                        update_fields=[
                            "current_step",
                            "last_email_sent_at",
                            "completed",
                        ]
                    )

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Sent to {batch_lead.email} - "
                            f"Step {step.step_number}"
                        )
                    )

                except Exception as e:

                    # --------------------------------
                    # LOG FAILED EMAIL
                    # --------------------------------

                    EmailLog.objects.create(
                        batch_lead=batch_lead,
                        template=step.template,
                        step_number=step.step_number,
                        to_email=batch_lead.email,
                        subject=step.template.subject,
                        status=EmailLog.Status.FAILED,
                        error=str(e),
                    )

                    self.stdout.write(
                        self.style.ERROR(
                            f"Failed {batch_lead.email}: {e}"
                        )
                    )
