import hashlib
import logging
from urllib.parse import quote

import requests
from django.conf import settings
from django.core import signing
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import BatchLead, EmailSuppression


logger = logging.getLogger(__name__)
UNSUBSCRIBE_TOKEN_SALT = "campaigns.email-unsubscribe"


def normalize_email(email):
    return email.strip().lower()


def get_unsubscribe_token(batch_lead):
    email = normalize_email(batch_lead.email)
    if not email:
        raise ValueError("Cannot create an unsubscribe link without a recipient email.")

    email_digest = hashlib.sha256(email.encode("utf-8")).hexdigest()
    return signing.dumps(
        {"batch_lead_id": batch_lead.pk, "email_digest": email_digest},
        salt=UNSUBSCRIBE_TOKEN_SALT,
        compress=True,
    )


def resolve_unsubscribe_token(token):
    try:
        payload = signing.loads(token, salt=UNSUBSCRIBE_TOKEN_SALT)
        batch_lead = BatchLead.objects.get(pk=payload["batch_lead_id"])
    except (
        signing.BadSignature,
        BatchLead.DoesNotExist,
        KeyError,
        TypeError,
        ValueError,
    ):
        return None

    expected_digest = hashlib.sha256(
        normalize_email(batch_lead.email).encode("utf-8")
    ).hexdigest()
    if not batch_lead.email or payload.get("email_digest") != expected_digest:
        return None

    return batch_lead


def get_unsubscribe_url(batch_lead):
    base_url = getattr(settings, "UNSUBSCRIBE_PUBLIC_BASE_URL", "").rstrip("/")
    if not base_url:
        raise ImproperlyConfigured(
            "UNSUBSCRIBE_PUBLIC_BASE_URL must be configured before sending campaign emails."
        )

    token = get_unsubscribe_token(batch_lead)
    return f"{base_url}{reverse('campaign-unsubscribe', kwargs={'token': token})}"


@transaction.atomic
def record_unsubscribe(email):
    normalized_email = normalize_email(email)
    if not normalized_email:
        raise ValueError("An email address is required to record an unsubscribe.")

    now = timezone.now()
    suppression, created = EmailSuppression.objects.get_or_create(
        email=normalized_email,
        defaults={"unsubscribed_at": now},
    )
    if not created:
        now = suppression.unsubscribed_at

    BatchLead.objects.filter(email__iexact=normalized_email).update(
        unsubscribed=True,
        unsubscribed_at=now,
    )
    return suppression


def suppressed_email_addresses(emails):
    normalized_emails = {normalize_email(email) for email in emails if email}
    if not normalized_emails:
        return set()
    return set(
        EmailSuppression.objects.filter(email__in=normalized_emails).values_list(
            "email", flat=True
        )
    )


def is_email_suppressed(email):
    if not email:
        return False
    return EmailSuppression.objects.filter(
        email=normalize_email(email)
    ).exists()


def sync_mailgun_suppression(email):
    anymail_settings = getattr(settings, "ANYMAIL", {})
    api_key = anymail_settings.get("MAILGUN_API_KEY")
    domain = anymail_settings.get("MAILGUN_SENDER_DOMAIN")
    if not api_key or not domain:
        raise ImproperlyConfigured(
            "Mailgun API key and sender domain are required to synchronize unsubscribe suppressions."
        )

    api_base_url = getattr(
        settings, "MAILGUN_API_BASE_URL", "https://api.mailgun.net"
    ).rstrip("/")
    endpoint = f"{api_base_url}/v3/{quote(domain, safe='')}/unsubscribes"
    response = requests.post(
        endpoint,
        auth=("api", api_key),
        data={"address": normalize_email(email)},
        timeout=10,
    )
    response.raise_for_status()
