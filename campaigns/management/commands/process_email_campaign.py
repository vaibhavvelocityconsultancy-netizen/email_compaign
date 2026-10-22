import os
import imaplib
import logging
from html import escape

from datetime import timedelta
from email.mime.image import MIMEImage

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone

from campaigns.models import Batch, BatchLead, Channel, EmailLog
from campaigns.unsubscribe import (
    get_unsubscribe_url,
    is_email_suppressed,
)

logger = logging.getLogger(__name__)


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

    def add_arguments(self, parser):
        parser.add_argument("--batch-id", type=int)
        parser.add_argument("--batch-lead-id", type=int)
        parser.add_argument(
            "--force",
            action="store_true",
            help="Send the next step immediately, ignoring its scheduled delay.",
        )

    @transaction.atomic
    def handle(self, *args, **kwargs):

        now = timezone.now()
        batch_id = kwargs.get("batch_id")
        batch_lead_id = kwargs.get("batch_lead_id")
        force = kwargs.get("force", False)

        # Get active batches
        active_batches = Batch.objects.filter(
            status=Batch.Status.ACTIVE,
            sequence__channel=Channel.EMAIL,
        ).select_related("sequence")
        if batch_id is not None:
            active_batches = active_batches.filter(pk=batch_id)

        if not active_batches.exists():
            if batch_id is not None:
                requested_batch = Batch.objects.filter(pk=batch_id).first()
                if requested_batch is None:
                    logger.warning(
                        "Skipping campaign processing: batch %s does not exist.",
                        batch_id,
                    )
                    message = f"Batch {batch_id} does not exist."
                elif requested_batch.status != Batch.Status.ACTIVE:
                    logger.info(
                        "Skipping batch %s: campaign status is %s.",
                        batch_id,
                        requested_batch.status,
                    )
                    message = (
                        f"Batch '{requested_batch.name}' is "
                        f"{requested_batch.status}, not active."
                    )
                else:
                    logger.info(
                        "Skipping batch %s: campaign channel is not email.",
                        batch_id,
                    )
                    message = f"Batch '{requested_batch.name}' is not an email campaign."
            else:
                logger.info("No active email campaigns are due for processing.")
                message = "No active batches found."
            self.stdout.write(
                self.style.WARNING(message)
            )
            return

        for batch in active_batches:

            # Get sequence steps
            steps = list(
                batch.sequence.steps.all().order_by("step_number")
            )

            if not steps:
                logger.warning(
                    "Skipping batch %s (%s): sequence %s has no steps.",
                    batch.pk,
                    batch.name,
                    batch.sequence_id,
                )
                self.stdout.write(
                    self.style.WARNING(
                        f"Batch '{batch.name}' has no sequence steps."
                    )
                )
                continue

            # Get leads that still need emails
            batch_leads = (
                batch.batch_leads.select_for_update()
                .select_related("lead", "lead__company", "lead__contact")
                .all()
            )
            if batch_lead_id is not None:
                batch_leads = batch_leads.filter(pk=batch_lead_id)

            if not batch_leads.exists():
                logger.warning(
                    "Batch %s (%s) has no recipient records to process.",
                    batch.pk,
                    batch.name,
                )
                self.stdout.write(
                    self.style.WARNING(
                        f"Batch '{batch.name}' has no recipient records."
                    )
                )
                continue

            for batch_lead in batch_leads:

                step = None
                try:
                    if batch_lead.replied:
                        logger.info(
                            "SKIP batch %s lead %s: recipient has replied.",
                            batch.pk,
                            batch_lead.lead_id,
                        )
                        continue
                    if batch_lead.unsubscribed:
                        logger.info(
                            "SKIP batch %s lead %s: recipient is unsubscribed.",
                            batch.pk,
                            batch_lead.lead_id,
                        )
                        continue
                    if batch_lead.completed:
                        logger.info(
                            "SKIP batch %s lead %s: sequence is already completed.",
                            batch.pk,
                            batch_lead.lead_id,
                        )
                        continue

                    if not batch_lead.email:
                        logger.warning(
                            "SKIP batch %s lead %s: no recipient email is available.",
                            batch.pk,
                            batch_lead.lead_id,
                        )
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
                        logger.warning(
                            "SKIP batch %s lead %s (%s): recipient is suppressed.",
                            batch.pk,
                            batch_lead.lead_id,
                            batch_lead.email,
                        )
                        self.stdout.write(
                            self.style.WARNING(
                                f"SKIP {batch_lead.email} - recipient is unsubscribed"
                            )
                        )
                        continue

                    # current_step starts from 0
                    current_step = batch_lead.current_step
                    if current_step < 0:
                        logger.warning(
                            "SKIP batch %s lead %s (%s): current_step %s is invalid.",
                            batch.pk,
                            batch_lead.lead_id,
                            batch_lead.email,
                            current_step,
                        )
                        continue

                    # No more steps
                    if current_step >= len(steps):
                        logger.info(
                            "Marking batch %s lead %s complete: current_step %s "
                            "is beyond the %s available steps.",
                            batch.pk,
                            batch_lead.lead_id,
                            current_step,
                            len(steps),
                        )
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
                            logger.warning(
                                "SKIP batch %s lead %s (%s): first step already has "
                                "a sent timestamp while current_step is 0.",
                                batch.pk,
                                batch_lead.lead_id,
                                batch_lead.email,
                            )
                            self.stdout.write(
                                f"SKIP {batch_lead.email} - "
                                f"Step 0 already sent"
                            )

                            continue

                        send_after = batch.created_at + timedelta(
                            days=step.delay_days,
                            minutes=step.delay_minutes
                        )

                    else:

                        # Follow-up requires previous email
                        if not batch_lead.last_email_sent_at:
                            logger.warning(
                                "SKIP batch %s lead %s (%s): current_step is %s but "
                                "there is no previous email timestamp.",
                                batch.pk,
                                batch_lead.lead_id,
                                batch_lead.email,
                                current_step,
                            )
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
                    if send_after > now and not force:
                        logger.info(
                            "SKIP batch %s lead %s (%s): step %s is due at %s "
                            "(now %s).",
                            batch.pk,
                            batch_lead.lead_id,
                            batch_lead.email,
                            step.step_number,
                            send_after,
                            now,
                        )
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
                    # --------------------------------
                    # CREATE EMAIL
                    # --------------------------------

                    from_email = getattr(
                        settings,
                        "DEFAULT_FROM_EMAIL",
                        settings.EMAIL_HOST_USER
                    )

                    reply_to_email = getattr(
                        batch,
                        "reply_to_email",
                        "",
                    )
                    reply_to_email = (
                        reply_to_email
                        or getattr(settings, "MAILGUN_REPLY_TO", from_email)
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
                    logger.info(
                        "Sent batch %s lead %s (%s), step %s.",
                        batch.pk,
                        batch_lead.lead_id,
                        batch_lead.email,
                        step.step_number,
                    )

                except Exception as e:
                    logger.exception(
                        "Failed sending batch %s lead %s (%s), step %s.",
                        batch.pk,
                        batch_lead.lead_id,
                        batch_lead.email,
                        step.step_number if step else "unknown",
                    )

                    # --------------------------------
                    # LOG FAILED EMAIL
                    # --------------------------------

                    if step is not None:
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
