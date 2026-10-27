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
from django.utils.html import format_html
from django.utils import timezone
from anymail.backends.mailgun import EmailBackend

from accounts.mailgun_secrets import decrypt_mailgun_secret
from accounts.models import TenantMailgunSettings
from campaigns.models import (
    Batch,
    BatchLead,
    Channel,
    EmailCampaignSettings,
    EmailLog,
    MessageTemplate,
)
from campaigns.unsubscribe import (
    get_unsubscribe_url,
    is_email_suppressed,
)

logger = logging.getLogger("email_campaign")


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
        parser.add_argument("--template-id", type=int)
        parser.add_argument("--enquiry-date")
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
        template_id = kwargs.get("template_id")
        enquiry_date = kwargs.get("enquiry_date")
        force = kwargs.get("force", False)
        template_override = (
            MessageTemplate.objects.filter(pk=template_id, channel=Channel.EMAIL).first()
            if template_id is not None
            else None
        )
        if template_id is not None and template_override is None:
            self.stdout.write(self.style.ERROR(f"Email template {template_id} does not exist."))
            return

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
            mailgun_settings = TenantMailgunSettings.objects.filter(
                tenant_id=batch.tenant_id
            ).first()
            tenant_connection = None
            if mailgun_settings is not None:
                tenant_connection = EmailBackend(
                    api_key=decrypt_mailgun_secret(
                        mailgun_settings.encrypted_api_key
                    ),
                    sender_domain=mailgun_settings.sender_domain,
                )

            # Get sequence steps
            steps = list(
                batch.sequence.steps.all().order_by("step_number")
            )

            if not steps:
                logger.warning(
                    "event=campaign.skipped campaign_id=%s reason=sequence_has_no_steps sequence_id=%s",
                    batch.pk,
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
                    "event=campaign.skipped campaign_id=%s reason=no_recipient_records",
                    batch.pk,
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
                    if not batch_lead.email:
                        current_email = (
                            batch_lead.lead.contact.email
                            if batch_lead.lead.contact
                            else ""
                        ) or batch_lead.lead.email
                        current_email = (current_email or "").strip()
                        if current_email:
                            batch_lead.email = current_email
                            batch_lead.save(update_fields=["email"])

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
                        batch_lead.email,
                        tenant_id=batch.tenant_id,
                    ):
                        if not batch_lead.unsubscribed:
                            batch_lead.unsubscribed = True
                            batch_lead.unsubscribed_at = timezone.now()
                            batch_lead.save(
                                update_fields=["unsubscribed", "unsubscribed_at"]
                            )
                        logger.warning(
                            "event=email_send.skipped campaign_id=%s lead_id=%s reason=suppressed",
                            batch.pk,
                            batch_lead.lead_id,
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
                            "event=email_send.skipped campaign_id=%s lead_id=%s reason=invalid_step current_step=%s",
                            batch.pk,
                            batch_lead.lead_id,
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
                                "event=email_send.skipped campaign_id=%s lead_id=%s reason=first_step_already_sent",
                                batch.pk,
                                batch_lead.lead_id,
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
                                "event=email_send.skipped campaign_id=%s lead_id=%s reason=missing_previous_sent_at current_step=%s",
                                batch.pk,
                                batch_lead.lead_id,
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
                            "event=email_send.skipped campaign_id=%s lead_id=%s reason=not_due step=%s due_at=%s",
                            batch.pk,
                            batch_lead.lead_id,
                            step.step_number,
                            send_after,
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

                    template = template_override or step.template

                    # --------------------------------
                    # LEAD DATA
                    # --------------------------------

                    lead = batch_lead.lead

                    company_name = lead.company.name if lead.company else ""
                    contact_name = lead.contact.name if lead.contact else ""
                    enquiry_for = lead.get_enquiry_for_display()
                    lead_enquiry_date = enquiry_date or (
                        lead.enquiry_date.isoformat() if lead.enquiry_date else ""
                    )

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
                    subject = subject.replace(
                        "{{enquiry_date}}",
                        lead_enquiry_date
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
                        "{{enquiry_date}}",
                        lead_enquiry_date
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
                    body += format_html(
                        '<br><br><p style="color:#666;font-size:12px;">'
                        'If you no longer want to receive these emails, '
                        '<a href="{}">unsubscribe here</a>.</p>',
                        unsubscribe_url,
                    )
                    # --------------------------------
                    # CREATE EMAIL
                    # --------------------------------

                    from_email = (
                        mailgun_settings.default_from_email
                        if mailgun_settings is not None
                        else getattr(
                            settings,
                            "DEFAULT_FROM_EMAIL",
                            settings.EMAIL_HOST_USER
                        )
                    )

                    reply_to_email = (
                        mailgun_settings.reply_to_email
                        if mailgun_settings is not None
                        else ""
                    )
                    if not reply_to_email:
                        reply_to_email = (
                            EmailCampaignSettings.objects.filter(
                                tenant_id=batch.tenant_id
                            )
                            .values_list("reply_to_email", flat=True)
                            .first()
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
                        connection=tenant_connection,
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

                    if is_email_suppressed(
                        batch_lead.email,
                        tenant_id=batch.tenant_id,
                    ):
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
                    mailgun_message_id = getattr(
                        getattr(msg, "anymail_status", None),
                        "message_id",
                        None,
                    )
                    if not mailgun_message_id:
                        raise RuntimeError(
                            "Mailgun accepted the email without returning a provider message ID."
                        )
                    mailgun_message_id = str(mailgun_message_id).strip().strip("<>").lower()

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
                        "event=email_send.sent campaign_id=%s lead_id=%s step=%s",
                        batch.pk,
                        batch_lead.lead_id,
                        step.step_number,
                    )

                except Exception as e:
                    logger.exception(
                        "event=email_send.failed campaign_id=%s lead_id=%s step=%s",
                        batch.pk,
                        batch_lead.lead_id,
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
