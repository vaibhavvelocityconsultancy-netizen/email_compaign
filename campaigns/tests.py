from django.test import TestCase
from rest_framework.test import APIClient

from .models import Batch, BatchLead, Channel, EmailLog, MessageLog, MessageTemplate, Sequence, Lead


class MessageLogListViewTests(TestCase):
	def test_lists_logs_with_batch_and_lead_ids(self):
		template = MessageTemplate.objects.create(
			name="Welcome",
			subject="Hello",
			body="Welcome aboard.",
		)
		sequence = Sequence.objects.create(name="Welcome sequence")
		batch = Batch.objects.create(name="April", sequence=sequence)
		lead = Lead.objects.create(
			name="Sam Example",
			email="sam@example.com",
			company="Example Co",
			phone="555-0100",
		)
		batch_lead = BatchLead.objects.create(
			batch=batch,
			lead=lead,
			email=lead.email,
		)
		message_log = EmailLog.objects.create(
			batch_lead=batch_lead,
			template=template,
			step_number=1,
			to_email=lead.email,
			subject=template.subject,
		)

		response = APIClient().get("/api/email-logs/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data[0]["id"], message_log.id)
		self.assertEqual(response.data[0]["batch"], batch.id)
		self.assertEqual(response.data[0]["lead"], lead.id)
		self.assertEqual(response.data[0]["template_name"], template.name)
		self.assertEqual(response.data[0]["channel"], Channel.EMAIL)


class CampaignSequenceAPITests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.template = MessageTemplate.objects.create(
			name="Welcome",
			subject="Hello",
			body="Welcome aboard.",
		)
		self.lead = Lead.objects.create(
			name="Sam Example",
			email="sam@example.com",
			company="Example Co",
			phone="555-0100",
		)

	def test_creates_and_replaces_sequence_steps(self):
		response = self.client.post(
			"/api/email-sequences/",
			{
				"name": "Welcome sequence",
				"description": "A short onboarding flow.",
				"steps": [
					{
						"step_number": 1,
						"template": self.template.id,
						"delay_days": 0,
						"delay_minutes": 0,
					}
				],
			},
			format="json",
		)

		self.assertEqual(response.status_code, 201, response.data)
		sequence_id = response.data["id"]
		self.assertEqual(len(response.data["steps"]), 1)

		update_response = self.client.patch(
			f"/api/email-sequences/{sequence_id}/",
			{
				"steps": [
					{
						"step_number": 1,
						"template": self.template.id,
						"delay_days": 2,
						"delay_minutes": 15,
					}
				]
			},
			format="json",
		)

		self.assertEqual(update_response.status_code, 200, update_response.data)
		self.assertEqual(update_response.data["steps"][0]["delay_days"], 2)
		self.assertEqual(update_response.data["steps"][0]["delay_minutes"], 15)

	def test_rejects_template_from_a_different_channel(self):
		whatsapp_template = MessageTemplate.objects.create(
			channel=Channel.WHATSAPP,
			name="WhatsApp welcome",
			body="Welcome.",
		)
		response = self.client.post(
			"/api/email-sequences/",
			{
				"channel": Channel.EMAIL,
				"name": "Mixed sequence",
				"steps": [{"step_number": 1, "template": whatsapp_template.id}],
			},
			format="json",
		)

		self.assertEqual(response.status_code, 400)

	def test_creates_campaign_with_selected_leads(self):
		sequence = Sequence.objects.create(name="Welcome sequence")
		response = self.client.post(
			"/api/batches/",
			{
				"name": "New lead campaign",
				"sequence": sequence.id,
				"lead_ids": [self.lead.id],
			},
			format="json",
		)

		self.assertEqual(response.status_code, 201, response.data)
		self.assertTrue(
			BatchLead.objects.filter(
				batch_id=response.data["id"],
				lead=self.lead,
				email=self.lead.email,
				phone=self.lead.phone,
			).exists()
		)

	def test_allows_whatsapp_only_lead_with_opt_in(self):
		lead = Lead.objects.create(
			name="Asha Example",
			company="Example Co",
			phone="+919876543210",
			whatsapp_opt_in=True,
		)

		self.assertIsNone(lead.email)
		self.assertTrue(lead.whatsapp_opt_in)