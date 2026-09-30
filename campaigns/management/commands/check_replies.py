import re
from datetime import datetime, timedelta, timezone as dt_timezone

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from campaigns.models import BatchLead, Channel, MessageLog


OWN_EMAILS = {
	"reply@***REMOVED***"
}

EVENT_STATUSES = {
	"accepted": MessageLog.Status.ACCEPTED,
	"delivered": MessageLog.Status.DELIVERED,
	"opened": MessageLog.Status.OPENED,
	"clicked": MessageLog.Status.CLICKED,
	"failed": MessageLog.Status.FAILED,
	"complained": MessageLog.Status.COMPLAINED,
	"unsubscribed": MessageLog.Status.UNSUBSCRIBED,
}

STATUS_RANK = {
	MessageLog.Status.ACCEPTED: 0,
	MessageLog.Status.SENT: 0,
	MessageLog.Status.DELIVERED: 1,
	MessageLog.Status.OPENED: 2,
	MessageLog.Status.READ: 2,
	MessageLog.Status.CLICKED: 3,
	MessageLog.Status.FAILED: 4,
	MessageLog.Status.COMPLAINED: 5,
	MessageLog.Status.UNSUBSCRIBED: 5,
	MessageLog.Status.REPLIED: 6,
}


class Command(BaseCommand):
	help = "Check Mailgun events for replies and update message logs"

	def handle(self, *args, **kwargs):
		anymail = getattr(settings, "ANYMAIL", {})
		api_key = anymail.get("MAILGUN_API_KEY")
		domain = anymail.get("MAILGUN_SENDER_DOMAIN")

		if not api_key or not domain:
			self.stdout.write(
				self.style.ERROR(
					"MAILGUN_API_KEY and MAILGUN_SENDER_DOMAIN must be configured in settings.py."
				)
			)
			return

		begin_dt = datetime.now(dt_timezone.utc) - timedelta(days=30)
		begin_str = begin_dt.strftime("%a, %d %b %Y %H:%M:%S UTC")

		for event_name in [*EVENT_STATUSES, "stored"]:
			events = self._get_events(api_key, domain, event_name, begin_str)
			if events is None:
				continue

			self.stdout.write(f"{event_name}: {len(events)} events")
			for event in events:
				if event_name == "stored":
					self._process_reply_event(event)
				else:
					self._process_delivery_event(event, event_name)

	def _get_events(self, api_key, domain, event_name, begin_str):
		try:
			response = requests.get(
				f"https://api.mailgun.net/v3/{domain}/events",
				auth=("api", api_key),
				params={
					"event": event_name,
					"limit": 100,
					"begin": begin_str,
					"ascending": "no",
				},
				timeout=30,
			)
		except requests.RequestException as error:
			self.stdout.write(self.style.ERROR(f"Mailgun request failed: {error}"))
			return None

		if response.status_code != 200:
			self.stdout.write(
				self.style.ERROR(
					f"Mailgun {event_name} API error ({response.status_code}): {response.text}"
				)
			)
			return None

		return response.json().get("items", [])

	def _process_delivery_event(self, event, event_name):
		log = self._find_log(event)
		if not log:
			return

		new_status = EVENT_STATUSES[event_name]
		if STATUS_RANK[new_status] < STATUS_RANK.get(log.status, 0):
			return

		if log.status != new_status:
			log.status = new_status
			log.error = "" if new_status != MessageLog.Status.FAILED else log.error
			log.save(update_fields=["status", "error"])
			self.stdout.write(
				self.style.SUCCESS(f"{new_status} {log.to_address} (log {log.id})")
			)

	def _process_reply_event(self, event):
		sender_email = self._sender_email(event)
		event_time = self._event_time(event)
		if not sender_email or sender_email in OWN_EMAILS or not event_time:
			return

		batch_lead = BatchLead.objects.filter(
			email__iexact=sender_email,
			replied=False,
		).first()
		if not batch_lead or not batch_lead.last_email_sent_at:
			return

		last_sent = batch_lead.last_email_sent_at
		if timezone.is_naive(last_sent):
			last_sent = timezone.make_aware(last_sent, dt_timezone.utc)
		if event_time <= last_sent:
			return

		batch_lead.replied = True
		batch_lead.replied_at = event_time
		batch_lead.save(update_fields=["replied", "replied_at"])

		latest_log = MessageLog.objects.filter(
			batch_lead=batch_lead,
			status__in=[
				MessageLog.Status.ACCEPTED,
				MessageLog.Status.DELIVERED,
				MessageLog.Status.OPENED,
				MessageLog.Status.CLICKED,
			],
		).order_by("-sent_at").first()
		if latest_log:
			latest_log.status = MessageLog.Status.REPLIED
			latest_log.save(update_fields=["status"])

		self.stdout.write(
			self.style.SUCCESS(f"Reply detected from {sender_email} at {event_time}")
		)

	def _find_log(self, event):
		message_id = self._message_id(event)
		if message_id:
			log = MessageLog.objects.filter(
				channel=Channel.EMAIL,
				provider_message_id=message_id,
			).first()
			if log:
				return log

		recipient = event.get("recipient", "").lower()
		if not recipient:
			return None

		return MessageLog.objects.filter(
			channel=Channel.EMAIL,
			to_address__iexact=recipient,
		).order_by("-sent_at").first()

	@staticmethod
	def _message_id(event):
		headers = event.get("message", {}).get("headers", {})
		return headers.get("message-id", "").strip().strip("<>").lower()

	@staticmethod
	def _sender_email(event):
		headers = event.get("message", {}).get("headers", {})
		match = re.search(r"[\w.+-]+@[\w.-]+", headers.get("from", ""))
		return match.group(0).lower() if match else ""

	@staticmethod
	def _event_time(event):
		try:
			return datetime.fromtimestamp(
				float(event.get("timestamp")),
				tz=dt_timezone.utc,
			)
		except (TypeError, ValueError, OSError):
			return None