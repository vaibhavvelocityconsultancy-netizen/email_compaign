import email
import imaplib
import re
import socket
import ssl
from datetime import timezone as datetime_timezone
from email import policy
from email.utils import getaddresses, parsedate_to_datetime

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone

from accounts.mailgun_secrets import decrypt_mailgun_secret, encrypt_mailgun_secret
from campaigns.gmail_sync import REPLY_LOG_STATUSES, _message_ids
from campaigns.models import (
    BatchLead,
    Channel,
    InboundReply,
    IonosMailbox,
    MessageLog,
)


class IonosMailboxError(Exception):
    pass


class IonosAuthenticationError(IonosMailboxError):
    pass


class IonosConnectionError(IonosMailboxError):
    pass


def _imap_settings():
    host = str(getattr(settings, "IONOS_IMAP_HOST", "imap.ionos.com")).strip()
    try:
        port = int(getattr(settings, "IONOS_IMAP_PORT", 993))
        timeout = int(getattr(settings, "IONOS_IMAP_TIMEOUT_SECONDS", 15))
    except (TypeError, ValueError) as error:
        raise IonosConnectionError("IONOS IMAP configuration is invalid.") from error
    if not host or not (1 <= port <= 65535) or timeout <= 0:
        raise IonosConnectionError("IONOS IMAP configuration is invalid.")
    return host, port, timeout


def _open_imap(email_address, password):
    host, port, timeout = _imap_settings()
    try:
        client = imaplib.IMAP4_SSL(
            host,
            port,
            ssl_context=ssl.create_default_context(),
            timeout=timeout,
        )
    except (OSError, socket.timeout, ssl.SSLError, imaplib.IMAP4.error) as error:
        raise IonosConnectionError("IONOS IMAP could not be reached.") from error

    try:
        status, _ = client.login(email_address, password)
        if status != "OK":
            raise IonosAuthenticationError(
                "IONOS rejected the mailbox credentials. Check the email and password."
            )
        status, _ = client.select("INBOX", readonly=True)
        if status != "OK":
            raise IonosConnectionError("IONOS could not open the mailbox inbox.")
        uid_validity = _response_number(client, "UIDVALIDITY")
        uid_next = _response_number(client, "UIDNEXT")
        if uid_validity is None:
            raise IonosConnectionError("IONOS did not return a mailbox UIDVALIDITY.")
        return client, str(uid_validity), uid_next
    except IonosMailboxError:
        try:
            client.logout()
        except Exception:
            pass
        raise
    except imaplib.IMAP4.error as error:
        try:
            client.logout()
        except Exception:
            pass
        if "AUTHENTICATIONFAILED" in str(error).upper() or "LOGIN" in str(error).upper():
            raise IonosAuthenticationError(
                "IONOS rejected the mailbox credentials. Check the email and password."
            ) from error
        raise IonosConnectionError("IONOS mailbox connection failed.") from error
    except (OSError, socket.timeout, ssl.SSLError) as error:
        try:
            client.logout()
        except Exception:
            pass
        raise IonosConnectionError("IONOS mailbox connection failed.") from error


def _response_number(client, name):
    try:
        _, values = client.response(name)
        if not values:
            return None
        match = re.search(rb"\d+", values[0] if isinstance(values[0], bytes) else str(values[0]).encode())
        return int(match.group()) if match else None
    except (AttributeError, TypeError, ValueError):
        return None


def validate_ionos_credentials(email_address, password):
    try:
        client, uid_validity, uid_next = _open_imap(email_address, password)
    finally:
        if "client" in locals():
            try:
                client.logout()
            except Exception:
                pass
    return uid_validity, uid_next


def _header_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _received_at(message):
    value = message.get("Date")
    if not value:
        return None
    try:
        received_at = parsedate_to_datetime(str(value))
    except (TypeError, ValueError, OverflowError):
        return None
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=datetime_timezone.utc)
    return received_at.astimezone(datetime_timezone.utc)


def _message_bodies(message):
    plain_parts = []
    html_parts = []
    for part in message.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            content = part.get_content()
        except (LookupError, UnicodeError, AttributeError):
            payload = part.get_payload(decode=True) or b""
            try:
                content = payload.decode(
                    part.get_content_charset() or "utf-8", errors="replace"
                )
            except LookupError:
                content = payload.decode("utf-8", errors="replace")
        if not isinstance(content, str):
            continue
        if content_type == "text/plain":
            plain_parts.append(content)
        else:
            html_parts.append(content)
    return "\n".join(plain_parts)[:200_000], "\n".join(html_parts)[:200_000]


def _sender_address(message):
    return next(
        (address.strip().lower() for _, address in getaddresses([str(message.get("From", ""))]) if address),
        "",
    )


def _recipient_address(message, mailbox_email):
    recipients = [
        address.strip().lower()
        for _, address in getaddresses([str(message.get("To", ""))])
        if address
    ]
    return next(
        (address for address in recipients if address.casefold() == mailbox_email.casefold()),
        recipients[0] if recipients else mailbox_email,
    )


def _match_campaign_log(sender, received_at, headers, tenant_id):
    logs = list(
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
    references = _message_ids(headers.get("in-reply-to", "")) | _message_ids(
        headers.get("references", "")
    )
    if references:
        for log in logs:
            if _message_ids(log.provider_message_id) & references:
                return log
        return None
    return logs[0] if len(logs) == 1 else None


def _raw_message(fetch_data):
    for item in fetch_data or []:
        if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
            return item[1]
    return None


def _save_reply(mailbox, uid_validity, uid, message):
    sender = _sender_address(message)
    if not sender or sender.casefold() == mailbox.email.casefold():
        return False

    received_at = _received_at(message)
    headers = {
        "in-reply-to": _header_text(message.get("In-Reply-To")),
        "references": _header_text(message.get("References")),
    }
    matched_log = (
        _match_campaign_log(sender, received_at, headers, mailbox.tenant_id)
        if received_at
        else None
    )
    plain_body, html_body = _message_bodies(message)
    message_id = _header_text(message.get("Message-ID")) or None
    source_key = f"ionos:{mailbox.pk}:{uid_validity}:{uid}"
    defaults = {
        "batch_lead": matched_log.batch_lead if matched_log else None,
        "sender_email": sender,
        "recipient_email": _recipient_address(message, mailbox.email),
        "subject": _header_text(message.get("Subject"))[:998],
        "body_plain": plain_body,
        "body_html": html_body,
        "message_id": message_id,
        "external_source_key": source_key,
        "received_at": received_at or timezone.now(),
        "tenant_id": mailbox.tenant_id,
    }
    if message_id:
        reply, created = InboundReply.objects.get_or_create(
            tenant_id=mailbox.tenant_id,
            message_id_hash=InboundReply.message_id_digest(message_id),
            defaults=defaults,
        )
    else:
        reply, created = InboundReply.objects.get_or_create(
            tenant_id=mailbox.tenant_id,
            external_source_key=source_key,
            defaults=defaults,
        )

    if matched_log:
        if reply.batch_lead_id is None:
            reply.batch_lead = matched_log.batch_lead
            reply.save(update_fields=["batch_lead"])
        locked_lead = BatchLead.objects.select_for_update().get(
            pk=matched_log.batch_lead_id
        )
        if not locked_lead.replied:
            locked_lead.replied = True
            locked_lead.replied_at = received_at or timezone.now()
            locked_lead.save(update_fields=["replied", "replied_at"])
        MessageLog.objects.filter(pk=matched_log.pk).update(
            status=MessageLog.Status.REPLIED
        )
    return created


def _sync_locked_mailbox(mailbox):
    if not mailbox.is_connected or not mailbox.encrypted_password:
        raise IonosMailboxError("IONOS mailbox is not connected.")
    try:
        password = decrypt_mailgun_secret(mailbox.encrypted_password)
    except (ImproperlyConfigured, ValueError, UnicodeError) as error:
        raise IonosMailboxError(
            "Stored IONOS credentials cannot be decrypted; reconnect the mailbox."
        ) from error

    client, current_validity, uid_next = _open_imap(mailbox.email, password)
    try:
        if mailbox.uid_validity and mailbox.uid_validity != current_validity:
            mailbox.last_uid = 0
        mailbox.uid_validity = current_validity
        start_uid = mailbox.last_uid + 1
        status, data = client.uid("search", None, f"UID {start_uid}:*")
        if status != "OK":
            raise IonosConnectionError("IONOS could not list new inbox messages.")
        uids = [
            int(value)
            for value in (data[0].split() if data and data[0] else [])
            if value.isdigit()
        ]
        processed_count = 0
        last_uid = mailbox.last_uid
        for uid in uids:
            status, fetch_data = client.uid("fetch", str(uid), "(RFC822)")
            if status != "OK":
                raise IonosConnectionError("IONOS could not download an inbox message.")
            raw_message = _raw_message(fetch_data)
            if raw_message is None:
                raise IonosConnectionError("IONOS returned an unreadable inbox message.")
            message = email.message_from_bytes(raw_message, policy=policy.default)
            if _save_reply(mailbox, current_validity, uid, message):
                processed_count += 1
            last_uid = max(last_uid, uid)

        mailbox.last_uid = max(last_uid, (uid_next or 1) - 1)
        mailbox.uid_validity = current_validity
        mailbox.last_sync_at = timezone.now()
        mailbox.last_error = ""
        mailbox.save(
            update_fields=[
                "last_uid",
                "uid_validity",
                "last_sync_at",
                "last_error",
                "updated_at",
            ]
        )
        return processed_count
    except (imaplib.IMAP4.error, OSError, socket.timeout, ssl.SSLError) as error:
        raise IonosConnectionError("IONOS inbox synchronization failed.") from error
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _sync_one_mailbox(mailbox_id):
    try:
        with transaction.atomic():
            mailbox = IonosMailbox.objects.select_for_update().filter(pk=mailbox_id).first()
            if mailbox is None:
                raise IonosMailboxError("IONOS mailbox was not found.")
            return _sync_locked_mailbox(mailbox)
    except IonosAuthenticationError:
        IonosMailbox.objects.filter(pk=mailbox_id).update(
            is_connected=False,
            last_error="Authentication failed; reconnect the mailbox.",
        )
        raise
    except IonosMailboxError as error:
        IonosMailbox.objects.filter(pk=mailbox_id).update(last_error=str(error)[:200])
        raise


def sync_ionos_replies(mailbox_id=None):
    if mailbox_id is not None:
        return _sync_one_mailbox(mailbox_id)

    mailbox_ids = list(
        IonosMailbox.objects.filter(is_connected=True)
        .exclude(encrypted_password="")
        .values_list("pk", flat=True)
    )
    processed_count = 0
    failures = []
    for identifier in mailbox_ids:
        try:
            processed_count += _sync_one_mailbox(identifier)
        except IonosMailboxError:
            failures.append(identifier)
    if failures:
        raise IonosMailboxError(
            f"IONOS sync failed for {len(failures)} mailbox(es); check connection status and server logs."
        )
    return processed_count
