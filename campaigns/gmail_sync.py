import re
import logging
from datetime import datetime, timezone as datetime_timezone
from email.utils import parseaddr

from django.db import transaction
from django.utils import timezone
from googleapiclient.errors import HttpError

from accounts.gmail_oauth import GmailOAuthError, get_gmail_service

from .models import (
    BatchLead,
    Channel,
    GmailMailbox,
    InboundReply,
    MessageLog,
)


logger = logging.getLogger(__name__)


METADATA_HEADERS = ("From", "To", "Date", "Message-ID", "In-Reply-To", "References")
REPLY_LOG_STATUSES = (
    MessageLog.Status.ACCEPTED,
    MessageLog.Status.SENT,
    MessageLog.Status.DELIVERED,
    MessageLog.Status.OPENED,
    MessageLog.Status.READ,
    MessageLog.Status.CLICKED,
    MessageLog.Status.REPLIED,
)


def _http_status(error):
    return getattr(getattr(error, "resp", None), "status", None)


def _header_map(message):
    headers = message.get("payload", {}).get("headers", [])
    return {
        str(header.get("name", "")).lower(): str(header.get("value", ""))
        for header in headers
    }


def _received_at(message):
    try:
        milliseconds = int(message["internalDate"])
        return datetime.fromtimestamp(milliseconds / 1000, tz=datetime_timezone.utc)
    except (KeyError, TypeError, ValueError, OSError):
        return None


def _message_ids(value):
    return {
        token.strip().strip("<>").casefold()
        for token in re.findall(r"<[^<>]+>|[^\s<>]+", value or "")
        if token.strip().strip("<>")
    }


def _match_campaign_log(sender, received_at, headers, tenant_id):
    logs = (
        MessageLog.objects.filter(
            channel=Channel.EMAIL,
            batch_lead__batch__tenant_id=tenant_id,
            to_address__iexact=sender,
            sent_at__lte=received_at,
            status__in=REPLY_LOG_STATUSES,
        )
        .select_related("batch_lead")
        .order_by("-sent_at")
    )
    reference_ids = _message_ids(headers.get("in-reply-to", "")) | _message_ids(
        headers.get("references", "")
    )
    if reference_ids:
        for log in logs:
            if _message_ids(log.provider_message_id) & reference_ids:
                return log
        return None
    return logs.first()


def _process_message(service, mailbox, gmail_message_id):
    try:
        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=gmail_message_id,
                format="metadata",
                metadataHeaders=list(METADATA_HEADERS),
            )
            .execute()
        )
    except HttpError as error:
        if _http_status(error) == 404:
            return False
        raise GmailOAuthError("Gmail message metadata could not be read.") from error
    return _process_message_data(mailbox, message, gmail_message_id)


def _history_messages(service, history_id):
    page_token = None
    latest_history_id = history_id
    message_ids = set()
    try:
        while True:
            response = (
                service.users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=history_id,
                    historyTypes=["messageAdded"],
                    pageToken=page_token,
                )
                .execute()
            )
            latest_history_id = str(response.get("historyId", latest_history_id))
            for history_record in response.get("history", []):
                latest_history_id = str(
                    history_record.get("id", latest_history_id)
                )
                for added in history_record.get("messagesAdded", []):
                    message_id = added.get("message", {}).get("id")
                    if message_id:
                        message_ids.add(message_id)
            page_token = response.get("nextPageToken")
            if not page_token:
                return sorted(message_ids), latest_history_id
    except HttpError as error:
        if _http_status(error) == 404:
            return None, None
        raise GmailOAuthError("Gmail history could not be read.") from error


def _recover_expired_history(service, mailbox):
    try:
        current_profile = service.users().getProfile(userId="me").execute()
    except HttpError as error:
        raise GmailOAuthError("Gmail profile metadata could not be read.") from error
    latest_history_id = str(current_profile.get("historyId", ""))
    if not latest_history_id:
        raise GmailOAuthError("Gmail returned no history cursor during recovery.")

    cutoff = mailbox.last_sync_at
    page_token = None
    processed_count = 0
    while True:
        try:
            response = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    maxResults=500,
                    pageToken=page_token,
                )
                .execute()
            )
        except HttpError as error:
            raise GmailOAuthError("Gmail inbox metadata could not be listed.") from error

        for listed_message in response.get("messages", []):
            message_id = listed_message.get("id")
            if not message_id:
                continue
            try:
                message = (
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=message_id,
                        format="metadata",
                        metadataHeaders=list(METADATA_HEADERS),
                    )
                    .execute()
                )
            except HttpError as error:
                if _http_status(error) == 404:
                    continue
                raise GmailOAuthError(
                    "Gmail inbox message metadata could not be read."
                ) from error
            received_at = _received_at(message)
            if received_at and (cutoff is None or received_at > cutoff):
                processed_count += _process_message_data(mailbox, message, message_id)

        page_token = response.get("nextPageToken")
        if not page_token:
            return latest_history_id, processed_count


def _process_message_data(mailbox, message, gmail_message_id):
    if {"DRAFT", "SENT", "SPAM", "TRASH"} & set(message.get("labelIds", [])):
        return False
    headers = _header_map(message)
    sender = parseaddr(headers.get("from", ""))[1].strip().lower()
    received_at = _received_at(message)
    if not sender or sender == mailbox.email.casefold() or received_at is None:
        return False

    matched_log = _match_campaign_log(
        sender,
        received_at,
        headers,
        mailbox.tenant_id,
    )
    if matched_log is None:
        return False

    batch_lead = matched_log.batch_lead
    dedupe_id = headers.get("message-id", "").strip() or f"gmail:{gmail_message_id}"
    with transaction.atomic():
        reply, created = InboundReply.objects.get_or_create(
            message_id_hash=InboundReply.message_id_digest(dedupe_id),
            defaults={
                "batch_lead": batch_lead,
                "sender_email": sender,
                "recipient_email": mailbox.email,
                "subject": headers.get("subject", ""),
                "body_plain": "",
                "body_html": "",
                "message_id": dedupe_id,
                "received_at": received_at,
                "tenant_id": mailbox.tenant_id,
            },
        )
        if reply.batch_lead_id is None:
            reply.batch_lead = batch_lead
            reply.save(update_fields=["batch_lead"])

        locked_batch_lead = BatchLead.objects.select_for_update().get(pk=batch_lead.pk)
        if not locked_batch_lead.replied:
            locked_batch_lead.replied = True
            locked_batch_lead.replied_at = received_at
            locked_batch_lead.save(update_fields=["replied", "replied_at"])
        MessageLog.objects.filter(pk=matched_log.pk).update(
            status=MessageLog.Status.REPLIED
        )
    return created


def sync_gmail_replies(mailbox_id=None):
    if mailbox_id is None:
        mailbox_ids = list(
            GmailMailbox.objects.filter(tenant__isnull=False)
            .exclude(encrypted_credentials="")
            .values_list(
                "pk",
                flat=True,
            )
        )
        if not mailbox_ids:
            raise GmailOAuthError("Gmail is not connected. Authorize a mailbox first.")
        processed_count = 0
        failed_mailbox_ids = []
        for identifier in mailbox_ids:
            try:
                processed_count += sync_gmail_replies(identifier)
            except Exception as error:
                failed_mailbox_ids.append(identifier)
                logger.warning(
                    "Gmail reply sync failed for mailbox_id=%s error_type=%s",
                    identifier,
                    type(error).__name__,
                )
        if failed_mailbox_ids:
            raise GmailOAuthError(
                f"Processed {processed_count} new message(s); sync failed for "
                f"{len(failed_mailbox_ids)} mailbox(es). Check connection status and logs."
            )
        return processed_count

    revoked_error = None
    with transaction.atomic():
        mailbox = GmailMailbox.objects.select_for_update().filter(pk=mailbox_id).first()
        if mailbox is None or not mailbox.encrypted_credentials:
            raise GmailOAuthError("Gmail is not connected. Authorize a mailbox first.")
        try:
            service = get_gmail_service(mailbox)
            message_ids, latest_history_id = _history_messages(
                service, mailbox.history_id
            )
            if message_ids is None:
                latest_history_id, processed_count = _recover_expired_history(
                    service, mailbox
                )
            else:
                processed_count = sum(
                    _process_message(service, mailbox, message_id)
                    for message_id in message_ids
                )
            mailbox.history_id = latest_history_id
            mailbox.last_sync_at = timezone.now()
            mailbox.save(update_fields=["history_id", "last_sync_at", "updated_at"])
        except GmailOAuthError as error:
            # get_gmail_service clears revoked credentials. Commit that state before
            # surfacing the error so the mailbox does not remain falsely connected.
            if mailbox.encrypted_credentials:
                raise
            revoked_error = error

    if revoked_error:
        raise revoked_error
    return processed_count
