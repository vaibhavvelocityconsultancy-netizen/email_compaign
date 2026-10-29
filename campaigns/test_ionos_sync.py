import socket
import imaplib
from datetime import timedelta
from email.utils import format_datetime
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.mailgun_secrets import encrypt_mailgun_secret
from accounts.models import Tenant
from .ionos_sync import (
    IonosAuthenticationError,
    IonosConnectionError,
    sync_ionos_replies,
    validate_ionos_credentials,
)
from .models import (
    Batch,
    BatchLead,
    Channel,
    InboundReply,
    IonosMailbox,
    Lead,
    MessageLog,
)


TEST_ENCRYPTION_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


class FakeImap:
    def __init__(self, raw_messages=None, uid_next=1000):
        self.raw_messages = raw_messages or {}
        self.uid_next = uid_next
        self.searched = []
        self.closed = False

    def login(self, _email, _password):
        return "OK", [b"LOGIN completed"]

    def select(self, _folder, readonly=True):
        return "OK", [b"1"]

    def response(self, name):
        return name, [b"789" if name == "UIDVALIDITY" else str(self.uid_next).encode()]

    def uid(self, command, *args):
        if command == "search":
            self.searched.append(args[-1])
            return "OK", [b" ".join(str(uid).encode() for uid in self.raw_messages)]
        uid = int(args[0])
        return "OK", [(b"message (RFC822)", self.raw_messages[uid])]

    def logout(self):
        self.closed = True
        return "BYE", [b"logout"]


@override_settings(
    GMAIL_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
    IONOS_IMAP_HOST="imap.ionos.com",
    IONOS_IMAP_PORT="993",
    IONOS_IMAP_TIMEOUT_SECONDS="5",
)
class IonosReplySyncTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="IONOS tenant")
        self.mailbox = IonosMailbox.objects.create(
            tenant=self.tenant,
            email="replies@example.com",
            encrypted_password=encrypt_mailgun_secret("mailbox-secret"),
            is_connected=True,
            uid_validity="789",
            last_uid=10,
        )
        self.received_at = timezone.now() + timedelta(minutes=2)
        self.raw_reply = (
            "From: Morgan Example <morgan@example.com>\r\n"
            "To: replies@example.com\r\n"
            "Subject: Re: Campaign\r\n"
            "Date: " + format_datetime(self.received_at) + "\r\n"
            "Message-ID: <reply-123@example.com>\r\n"
            "In-Reply-To: <campaign-123@example.com>\r\n"
            "References: <campaign-123@example.com>\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n\r\n"
            "Please send more details."
        ).encode()

        self.batch = Batch.objects.create(name="IONOS campaign", tenant=self.tenant)
        self.lead = Lead.objects.create(
            name="Morgan Example",
            email="morgan@example.com",
            tenant=self.tenant,
        )
        self.batch_lead = BatchLead.objects.create(
            batch=self.batch,
            lead=self.lead,
            email=self.lead.email,
            last_email_sent_at=timezone.now(),
        )
        self.message_log = MessageLog.objects.create(
            batch_lead=self.batch_lead,
            channel=Channel.EMAIL,
            step_number=1,
            to_address=self.lead.email,
            provider_message_id="<campaign-123@example.com>",
            sent_at=timezone.now(),
        )

    @patch("campaigns.ionos_sync.imaplib.IMAP4_SSL")
    def test_connection_uses_tls_and_validates_mailbox(self, imap_class):
        client = FakeImap()
        imap_class.return_value = client

        uid_validity, uid_next = validate_ionos_credentials(
            "replies@example.com", "mailbox-secret"
        )

        self.assertEqual((uid_validity, uid_next), ("789", 1000))
        self.assertTrue(client.closed)
        imap_class.assert_called_once()
        self.assertEqual(imap_class.call_args.args[:2], ("imap.ionos.com", 993))
        self.assertEqual(imap_class.call_args.kwargs["timeout"], 5)

    @patch("campaigns.ionos_sync.imaplib.IMAP4_SSL")
    def test_invalid_login_is_classified_as_authentication_failure(self, imap_class):
        client = Mock()
        client.login.side_effect = imaplib.IMAP4.error("AUTHENTICATIONFAILED")
        imap_class.return_value = client

        with self.assertRaises(IonosAuthenticationError):
            validate_ionos_credentials("replies@example.com", "bad-secret")

    @patch("campaigns.ionos_sync.imaplib.IMAP4_SSL")
    def test_new_reply_matches_campaign_and_retry_does_not_duplicate(self, imap_class):
        client = FakeImap({11: self.raw_reply}, uid_next=12)
        imap_class.return_value = client

        first_count = sync_ionos_replies(self.mailbox.pk)
        second_count = sync_ionos_replies(self.mailbox.pk)

        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 0)
        self.assertEqual(InboundReply.objects.count(), 1)
        reply = InboundReply.objects.get()
        self.assertEqual(reply.batch_lead_id, self.batch_lead.pk)
        self.assertEqual(reply.body_plain, "Please send more details.")
        self.batch_lead.refresh_from_db()
        self.message_log.refresh_from_db()
        self.assertTrue(self.batch_lead.replied)
        self.assertEqual(self.message_log.status, MessageLog.Status.REPLIED)
        self.mailbox.refresh_from_db()
        self.assertEqual(self.mailbox.last_uid, 11)
        self.assertTrue(self.mailbox.last_sync_at)

    @patch("campaigns.ionos_sync.imaplib.IMAP4_SSL")
    def test_unmatched_message_is_saved_without_campaign_association(self, imap_class):
        raw = self.raw_reply.replace(b"morgan@example.com", b"unknown@example.com")
        imap_class.return_value = FakeImap({11: raw}, uid_next=12)

        count = sync_ionos_replies(self.mailbox.pk)

        self.assertEqual(count, 1)
        reply = InboundReply.objects.get()
        self.assertIsNone(reply.batch_lead_id)
        self.assertTrue(reply.external_source_key.startswith("ionos:"))

    @patch("campaigns.ionos_sync.imaplib.IMAP4_SSL", side_effect=socket.timeout)
    def test_network_failure_does_not_advance_uid_cursor(self, _imap_class):
        with self.assertRaises(IonosConnectionError):
            sync_ionos_replies(self.mailbox.pk)

        self.mailbox.refresh_from_db()
        self.assertEqual(self.mailbox.last_uid, 10)
        self.assertEqual(self.mailbox.last_error, "IONOS IMAP could not be reached.")
