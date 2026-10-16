import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Batch,
    BatchLead,
    EmailSuppression,
    Lead,
    Sequence,
)
from .unsubscribe import get_unsubscribe_token, resolve_unsubscribe_token


class UnsubscribeFlowTests(TestCase):
    def setUp(self):
        sequence = Sequence.objects.create(name="Unsubscribe test")
        batch = Batch.objects.create(name="Test batch", sequence=sequence)
        lead = Lead.objects.create(name="Test recipient")
        self.batch_lead = BatchLead.objects.create(
            batch=batch,
            lead=lead,
            email="Recipient@Example.com",
        )

    def test_signed_token_is_bound_to_recipient_and_batch_lead(self):
        token = get_unsubscribe_token(self.batch_lead)

        self.assertEqual(resolve_unsubscribe_token(token), self.batch_lead)
        self.assertIsNone(resolve_unsubscribe_token("invalid-token"))

        self.batch_lead.email = "changed@example.com"
        self.batch_lead.save(update_fields=["email"])
        self.assertIsNone(resolve_unsubscribe_token(token))

    def test_confirmation_get_does_not_unsubscribe(self):
        token = get_unsubscribe_token(self.batch_lead)

        response = self.client.get(
            reverse("campaign-unsubscribe", kwargs={"token": token})
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["completed"])
        self.assertFalse(EmailSuppression.objects.exists())
        self.batch_lead.refresh_from_db()
        self.assertFalse(self.batch_lead.unsubscribed)

    def test_confirmation_post_records_suppression_for_every_batch(self):
        token = get_unsubscribe_token(self.batch_lead)
        with patch("campaigns.views.sync_mailgun_suppression") as sync_mailgun:
            response = self.client.post(
                    reverse("campaign-unsubscribe", kwargs={"token": token})
                )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["completed"])
        sync_mailgun.assert_called_once_with("Recipient@Example.com")
        suppression = EmailSuppression.objects.get(email="recipient@example.com")
        self.assertTrue(suppression.unsubscribed_at)
        self.batch_lead.refresh_from_db()
        self.assertTrue(self.batch_lead.unsubscribed)
        self.assertEqual(self.batch_lead.unsubscribed_at, suppression.unsubscribed_at)

    @override_settings(
        ANYMAIL={"MAILGUN_WEBHOOK_SIGNING_KEY": "test-signing-key"}
    )
    def test_mailgun_unsubscribe_suppresses_without_a_message_log(self):
        timestamp = str(int(timezone.now().timestamp()))
        token = "mailgun-token"
        signature = hmac.new(
            b"test-signing-key",
            f"{timestamp}{token}".encode(),
            hashlib.sha256,
        ).hexdigest()
        payload = {
            "signature": {
                "timestamp": timestamp,
                "token": token,
                "signature": signature,
            },
            "event-data": {
                "event": "unsubscribed",
                "recipient": "RECIPIENT@example.com",
            },
        }

        response = self.client.post(
            reverse("mailgun-webhook"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "suppressed")
        self.assertTrue(
            EmailSuppression.objects.filter(email="recipient@example.com").exists()
        )
        self.batch_lead.refresh_from_db()
        self.assertTrue(self.batch_lead.unsubscribed)

    @override_settings(
        ANYMAIL={"MAILGUN_WEBHOOK_SIGNING_KEY": "test-signing-key"}
    )
    def test_mailgun_unsubscribe_rejects_invalid_signature(self):
        payload = {
            "signature": {
                "timestamp": "1",
                "token": "invalid",
                "signature": "invalid",
            },
            "event-data": {
                "event": "unsubscribed",
                "recipient": "recipient@example.com",
            },
        }

        response = self.client.post(
            reverse("mailgun-webhook"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(EmailSuppression.objects.exists())
