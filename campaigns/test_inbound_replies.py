import hashlib
import hmac
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Batch, BatchLead, Channel, InboundReply, Lead, MessageLog


SIGNING_KEY = "inbound-webhook-test-signing-key"


@override_settings(ANYMAIL={"MAILGUN_WEBHOOK_SIGNING_KEY": SIGNING_KEY})
class InboundReplyWebhookTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.batch = Batch.objects.create(name="Reply campaign")
        self.lead = Lead.objects.create(
            name="Morgan Example",
            email="morgan@example.com",
        )
        self.batch_lead = BatchLead.objects.create(
            batch=self.batch,
            lead=self.lead,
            email=self.lead.email,
        )
        self.message_log = MessageLog.objects.create(
            batch_lead=self.batch_lead,
            channel=Channel.EMAIL,
            step_number=1,
            to_address=self.lead.email,
            subject="Initial message",
        )

    def signed_payload(self, **values):
        timestamp = "1790000000"
        token = "unique-webhook-token"
        signature = hmac.new(
            SIGNING_KEY.encode(),
            f"{timestamp}{token}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return {
            "timestamp": timestamp,
            "token": token,
            "signature": signature,
            **values,
        }

    def test_valid_reply_discards_content_matches_lead_and_updates_message_status(self):
        response = self.client.post(
            reverse("mailgun-inbound-webhook"),
            self.signed_payload(
                sender="Morgan@Example.com",
                recipient="replies@example.com",
                subject="Re: Initial message",
                **{
                    "body-plain": "Thanks, please send more details.",
                    "body-html": "<p>Thanks, please send more details.</p>",
                    "Message-Id": "<reply-123@example.com>",
                },
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "updated")
        reply = InboundReply.objects.get()
        self.assertEqual(reply.batch_lead, self.batch_lead)
        self.assertEqual(reply.sender_email, "morgan@example.com")
        self.assertEqual(reply.recipient_email, "replies@example.com")
        self.assertEqual(reply.subject, "")
        self.assertEqual(reply.body_plain, "")
        self.assertEqual(reply.body_html, "")
        self.assertEqual(reply.message_id, "<reply-123@example.com>")
        self.assertEqual(
            reply.message_id_hash,
            InboundReply.message_id_digest("<reply-123@example.com>"),
        )

        self.batch_lead.refresh_from_db()
        self.message_log.refresh_from_db()
        self.assertTrue(self.batch_lead.replied)
        self.assertIsNotNone(self.batch_lead.replied_at)
        self.assertEqual(self.message_log.status, MessageLog.Status.REPLIED)

    def test_invalid_signature_is_rejected_without_saving(self):
        response = self.client.post(
            reverse("mailgun-inbound-webhook"),
            {
                "timestamp": "1790000000",
                "token": "invalid",
                "signature": "invalid",
                "sender": "morgan@example.com",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(InboundReply.objects.count(), 0)

    def test_inbound_webhook_requires_post(self):
        response = self.client.get(reverse("mailgun-inbound-webhook"))

        self.assertEqual(response.status_code, 405)

    def test_unmatched_sender_is_saved_without_lead(self):
        response = self.client.post(
            reverse("mailgun-inbound-webhook"),
            self.signed_payload(
                sender="unknown@example.com",
                recipient="replies@example.com",
                subject="General question",
                **{"body-plain": "Can you help me?", "Message-Id": "<unknown-1>"},
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ignored")
        reply = InboundReply.objects.get()
        self.assertIsNone(reply.batch_lead)
        self.assertEqual(reply.subject, "")
        self.assertEqual(reply.body_plain, "")
        self.assertEqual(reply.body_html, "")

    def test_duplicate_delivery_does_not_create_another_reply(self):
        payload = self.signed_payload(
            sender="morgan@example.com",
            recipient="replies@example.com",
            subject="Re: Initial message",
            **{"body-plain": "One reply", "Message-Id": "<duplicate-1>"},
        )

        first_response = self.client.post(reverse("mailgun-inbound-webhook"), payload)
        second_response = self.client.post(reverse("mailgun-inbound-webhook"), payload)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(InboundReply.objects.count(), 1)
        self.message_log.refresh_from_db()
        self.assertEqual(self.message_log.status, MessageLog.Status.REPLIED)

    def test_late_mailgun_delivery_event_does_not_overwrite_replied_status(self):
        self.message_log.status = MessageLog.Status.REPLIED
        self.message_log.save(update_fields=["status"])
        response = self.client.post(
            reverse("mailgun-webhook"),
            {
                "signature": {
                    "timestamp": "1790000000",
                    "token": "unique-webhook-token",
                    "signature": hmac.new(
                        SIGNING_KEY.encode(),
                        b"1790000000unique-webhook-token",
                        hashlib.sha256,
                    ).hexdigest(),
                },
                "event-data": {
                    "event": "delivered",
                    "recipient": self.lead.email,
                    "message": {"headers": {}},
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "unchanged")
        self.message_log.refresh_from_db()
        self.assertEqual(self.message_log.status, MessageLog.Status.REPLIED)

    def test_missing_message_id_is_stored_without_preventing_another_reply(self):
        payload = self.signed_payload(
            sender="morgan@example.com",
            recipient="replies@example.com",
            subject="Reply without an ID",
            **{"body-plain": "No message ID"},
        )

        self.client.post(reverse("mailgun-inbound-webhook"), payload)
        self.client.post(reverse("mailgun-inbound-webhook"), payload)

        self.assertEqual(InboundReply.objects.count(), 2)
        self.assertTrue(
            all(reply.message_id is None for reply in InboundReply.objects.all())
        )


class InboundReplyApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="inboundreplyviewer",
            email="inboundreplyviewer@example.com",
            password="not-a-real-password",
        )
        self.client = APIClient()
        self.batch = Batch.objects.create(
            name="Filtered campaign", tenant=self.user.tenant
        )
        self.lead = Lead.objects.create(
            name="Taylor Example",
            email="taylor@example.com",
            tenant=self.user.tenant,
        )
        self.batch_lead = BatchLead.objects.create(
            batch=self.batch,
            lead=self.lead,
            email=self.lead.email,
        )
        self.reply = InboundReply.objects.create(
            batch_lead=self.batch_lead,
            sender_email=self.lead.email,
            recipient_email="replies@example.com",
            subject="A reply",
            body_plain="Reply body",
            message_id="<api-reply@example.com>",
            tenant=self.user.tenant,
        )

    def test_list_requires_authentication(self):
        response = self.client.get(reverse("inbound-reply-list"))

        self.assertEqual(response.status_code, 401)

    def test_authenticated_list_and_detail_include_related_lead_and_campaign(self):
        self.client.force_authenticate(user=self.user)
        older_reply = InboundReply.objects.create(
            sender_email="unmatched@example.com",
            recipient_email="replies@example.com",
            subject="Older reply",
            body_plain="An older message",
            message_id="<older-reply@example.com>",
            received_at=timezone.now() - timedelta(days=1),
            tenant=self.user.tenant,
        )

        list_response = self.client.get(reverse("inbound-reply-list"))
        detail_response = self.client.get(
            reverse("inbound-reply-detail", args=[self.reply.pk])
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in list_response.data],
            [self.reply.pk, older_reply.pk],
        )
        self.assertEqual(list_response.data[0]["lead"]["id"], self.lead.pk)
        self.assertEqual(list_response.data[0]["campaign"]["id"], self.batch.pk)
        self.assertEqual(list_response.data[0]["status"], MessageLog.Status.REPLIED)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data["body_plain"], "Reply body")
        self.assertNotIn("body_html", detail_response.data)
        self.assertEqual(detail_response.data["subject"], "A reply")

    def test_list_filters_by_lead_and_batch(self):
        self.client.force_authenticate(user=self.user)

        by_lead = self.client.get(
            reverse("inbound-reply-list"), {"lead": self.lead.pk}
        )
        by_batch = self.client.get(
            reverse("inbound-reply-list"), {"batch": self.batch.pk}
        )
        invalid_filter = self.client.get(
            reverse("inbound-reply-list"), {"batch": "not-a-number"}
        )

        self.assertEqual(len(by_lead.data), 1)
        self.assertEqual(len(by_batch.data), 1)
        self.assertEqual(invalid_filter.status_code, 400)
