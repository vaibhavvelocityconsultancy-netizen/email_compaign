from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone
from googleapiclient.errors import HttpError

from .gmail_sync import sync_gmail_replies
from .models import Batch, BatchLead, Channel, GmailMailbox, InboundReply, Lead, MessageLog


class GmailReplySyncTests(TestCase):
    def setUp(self):
        self.mailbox = GmailMailbox.objects.create(
            pk=1,
            email="replies@example.com",
            encrypted_credentials="encrypted-test-value",
            history_id="100",
            last_sync_at=timezone.now(),
        )
        self.batch = Batch.objects.create(name="Gmail campaign")
        self.lead = Lead.objects.create(
            name="Morgan Example",
            email="morgan@example.com",
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
        received_at = timezone.now() + timedelta(minutes=1)
        self.gmail_message = {
            "id": "gmail-message-456",
            "threadId": "gmail-thread-1",
            "internalDate": str(int(received_at.timestamp() * 1000)),
            "labelIds": ["INBOX"],
            "payload": {
                "headers": [
                    {"name": "From", "value": "Morgan Example <morgan@example.com>"},
                    {"name": "To", "value": "replies@example.com"},
                    {"name": "Message-ID", "value": "<reply-456@example.com>"},
                    {
                        "name": "In-Reply-To",
                        "value": "<campaign-123@example.com>",
                    },
                    {
                        "name": "References",
                        "value": "<campaign-123@example.com>",
                    },
                ]
            },
        }
        self.history_list = Mock(
            return_value={
                "historyId": "101",
                "history": [
                    {
                        "id": "101",
                        "messagesAdded": [
                            {"message": {"id": "gmail-message-456"}}
                        ],
                    }
                ],
            }
        )
        self.message_get = Mock(return_value=self.gmail_message)
        messages = Mock()
        messages.list.return_value.execute.return_value = {"messages": []}
        messages.get.side_effect = lambda **kwargs: Mock(
            execute=Mock(return_value=self.message_get(**kwargs))
        )
        history = Mock()
        history.list.side_effect = lambda **kwargs: Mock(
            execute=Mock(return_value=self.history_list(**kwargs))
        )
        users = Mock()
        users.messages.return_value = messages
        users.history.return_value = history
        self.service = Mock()
        self.service.users.return_value = users

    @patch("campaigns.gmail_sync.get_gmail_service")
    def test_history_reply_updates_existing_campaign_records_without_content(self, get_service):
        get_service.return_value = self.service

        processed = sync_gmail_replies()

        self.assertEqual(processed, 1)
        self.batch_lead.refresh_from_db()
        self.message_log.refresh_from_db()
        reply = InboundReply.objects.get()
        self.assertTrue(self.batch_lead.replied)
        self.assertEqual(self.batch_lead.replied_at, datetime.fromtimestamp(
            int(self.gmail_message["internalDate"]) / 1000,
            tz=datetime_timezone.utc,
        ))
        self.assertEqual(self.message_log.status, MessageLog.Status.REPLIED)
        self.assertEqual(reply.batch_lead, self.batch_lead)
        self.assertEqual(reply.message_id, "<reply-456@example.com>")
        self.assertEqual(reply.subject, "")
        self.assertEqual(reply.body_plain, "")
        self.assertEqual(reply.body_html, "")
        self.message_get.assert_called_once()
        self.assertEqual(
            self.message_get.call_args.kwargs["format"],
            "metadata",
        )

    @patch("campaigns.gmail_sync.get_gmail_service")
    def test_duplicate_history_delivery_is_idempotent(self, get_service):
        get_service.return_value = self.service

        sync_gmail_replies()
        sync_gmail_replies()

        self.assertEqual(InboundReply.objects.count(), 1)
        self.assertEqual(self.message_get.call_count, 2)

    @patch("campaigns.gmail_sync.get_gmail_service")
    def test_expired_history_cursor_recovers_from_message_metadata(self, get_service):
        service = Mock()
        users = Mock()
        history_response = Mock()
        history_response.execute.side_effect = HttpError(
            Mock(status=404, reason="Not Found"),
            b"expired history cursor",
        )
        users.history.return_value.list.return_value = history_response
        users.getProfile.return_value.execute.return_value = {"historyId": "102"}
        users.messages.return_value.list.return_value.execute.return_value = {
            "messages": [{"id": "gmail-message-456"}]
        }
        users.messages.return_value.get.return_value.execute.return_value = self.gmail_message
        service.users.return_value = users
        get_service.return_value = service

        processed = sync_gmail_replies()

        self.assertEqual(processed, 1)
        self.mailbox.refresh_from_db()
        self.assertEqual(self.mailbox.history_id, "102")
        self.assertEqual(InboundReply.objects.count(), 1)
        self.assertEqual(users.messages.return_value.list.call_args.kwargs["userId"], "me")

    @patch("campaigns.gmail_sync.get_gmail_service")
    def test_unmatched_reply_headers_do_not_fall_back_to_sender_only(self, get_service):
        self.gmail_message["payload"]["headers"] = [
            {"name": "From", "value": "morgan@example.com"},
            {"name": "Message-ID", "value": "<unrelated-reply@example.com>"},
            {"name": "In-Reply-To", "value": "<not-our-campaign@example.com>"},
        ]
        get_service.return_value = self.service

        sync_gmail_replies()

        self.batch_lead.refresh_from_db()
        self.message_log.refresh_from_db()
        self.assertFalse(self.batch_lead.replied)
        self.assertEqual(self.message_log.status, MessageLog.Status.ACCEPTED)
        self.assertEqual(InboundReply.objects.count(), 0)
