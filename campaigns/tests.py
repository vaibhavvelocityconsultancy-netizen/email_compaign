import csv
import io
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test.utils import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    Batch,
    
    BatchLead,
    Channel,
    City,
    Company,
    CompanyContact,
    Country,
<<<<<<< HEAD
    EmailCampaignSettings,
=======
>>>>>>> 612c1c9aa8f3fdd9f0332a8f1776fd6ed878a789
    Lead,
    MessageTemplate,
    Opportunity,
    OpportunityModule,
    Quotation,
    QuotationItem,
    SalesOrder,
    Sequence,
    SequenceStep,
    State,
    Task,
)
from .serializers import LeadSerializer
from .unsubscribe import get_unsubscribe_url


class LeadSampleDataApiTests(TestCase):
	def setUp(self):
		user = get_user_model().objects.create_user(
			username="sample-lead-test",
			email="sample-lead-test@example.com",
			password="test-password",
		)
		self.client = APIClient()
		self.client.force_authenticate(user=user)

	def test_template_download_seed_endpoint_is_idempotent(self):
		first_response = self.client.post("/api/leads/sample-data/")
		second_response = self.client.post("/api/leads/sample-data/")

		self.assertEqual(first_response.status_code, 200)
		self.assertEqual(first_response.data, {"created": 3, "existing": 0})
		self.assertEqual(second_response.status_code, 200)
		self.assertEqual(second_response.data, {"created": 0, "existing": 3})
		self.assertEqual(Lead.objects.count(), 3)

	def test_csv_import_skips_seeded_sample_leads_as_duplicates(self):
		self.client.post("/api/leads/sample-data/")
		csv_file = SimpleUploadedFile(
			"lead-import.csv",
			b"contact_email\nAarav.Mehta@example.com\n",
			content_type="text/csv",
		)

		response = self.client.post(
			"/api/leads/import-csv/",
			{"file": csv_file},
			format="multipart",
		)

		self.assertEqual(response.status_code, 201, response.data)
		self.assertEqual(response.data["duplicates"], 1)
		self.assertEqual(response.data["imported"], 0)
		self.assertEqual(Lead.objects.count(), 3)

	def test_csv_import_reimports_leads_after_soft_delete(self):
		self.client.post("/api/leads/sample-data/")
		Lead.objects.update(is_active=False)
		csv_file = SimpleUploadedFile(
			"lead-import.csv",
			(
				b"contact_email\n"
				b"aarav.mehta@example.com\n"
				b"diya.sharma@example.com\n"
				b"kabir.patel@example.com\n"
			),
			content_type="text/csv",
		)

		response = self.client.post(
			"/api/leads/import-csv/",
			{"file": csv_file},
			format="multipart",
		)

		self.assertEqual(response.status_code, 201, response.data)
		self.assertEqual(response.data["total_rows"], 3)
		self.assertEqual(response.data["imported"], 3)
		self.assertEqual(response.data["duplicates"], 0)
		self.assertEqual(response.data["invalid"], 0)
		self.assertEqual(Lead.objects.filter(is_active=True).count(), 3)

	def test_delete_lead_permanently_removes_it_and_allows_reimport(self):
		self.client.post("/api/leads/sample-data/")
		lead = Lead.objects.get(contact__email="aarav.mehta@example.com")

		delete_response = self.client.delete(f"/api/leads/{lead.pk}/")

		self.assertEqual(delete_response.status_code, 204)
		self.assertFalse(Lead.objects.filter(pk=lead.pk).exists())
		csv_file = SimpleUploadedFile(
			"lead-import.csv",
			b"contact_email\nAarav.Mehta@example.com\n",
			content_type="text/csv",
		)
		import_response = self.client.post(
			"/api/leads/import-csv/",
			{"file": csv_file},
			format="multipart",
		)

		self.assertEqual(import_response.status_code, 201, import_response.data)
		self.assertEqual(import_response.data["imported"], 1)
		self.assertEqual(import_response.data["duplicates"], 0)
		self.assertEqual(Lead.objects.filter(is_active=True).count(), 3)


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


class CampaignSendNowApiTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(
			username="campaignsendnow",
			email="campaignsendnow@example.com",
			password="test-password",
		)
		self.client = APIClient()
		self.client.force_authenticate(user=self.user)
		self.sequence = Sequence.objects.create(name="Send now sequence")
		self.batch = Batch.objects.create(
			name="Send now campaign",
			sequence=self.sequence,
			reply_to_email="replies@example.com",
		)
		self.lead = Lead.objects.create(
			name="Example recipient",
			email="recipient@example.com",
		)
		self.batch_lead = BatchLead.objects.create(
			batch=self.batch,
			lead=self.lead,
			email=self.lead.email,
		)

	@patch("campaigns.views.call_command")
	def test_campaign_and_individual_lead_send_now(self, call_command_mock):
		def write_success(_command, **options):
			options["stdout"].write("Sent to recipient@example.com - Step 1\n")

		call_command_mock.side_effect = write_success

		campaign_response = self.client.post(
			f"/api/batches/{self.batch.pk}/send-now/"
		)
		lead_response = self.client.post(
			f"/api/batches/{self.batch.pk}/leads/{self.lead.pk}/send-now/"
		)

		self.assertEqual(campaign_response.status_code, 200, campaign_response.data)
		self.assertEqual(campaign_response.data, {"sent": 1, "failed": 0})
		self.assertEqual(lead_response.status_code, 200, lead_response.data)
		self.assertEqual(lead_response.data, {"sent": 1, "failed": 0})
		self.assertEqual(call_command_mock.call_count, 2)
		self.assertTrue(call_command_mock.call_args_list[0].kwargs["force"])
		self.assertEqual(
			call_command_mock.call_args_list[1].kwargs["batch_lead_id"],
			self.batch_lead.pk,
		)

	def test_paused_campaign_cannot_be_sent_manually(self):
		self.batch.status = Batch.Status.PAUSED
		self.batch.save(update_fields=["status"])

		response = self.client.post(f"/api/batches/{self.batch.pk}/send-now/")

		self.assertEqual(response.status_code, 400)
		self.assertIn("Resume this campaign", response.data["detail"])

	@patch("campaigns.views.call_command")
	def test_one_time_campaign_sends_selected_template_without_sequence(self, call_command_mock):
		def write_success(_command, **options):
			options["stdout"].write("Sent to recipient@example.com - Step 1\n")

		call_command_mock.side_effect = write_success
		template = MessageTemplate.objects.create(
			name="One-time template",
			subject="Hello",
			body="Hello there.",
		)
		self.lead.enquiry_date = date(2026, 10, 22)
		self.lead.save(update_fields=["enquiry_date"])
		batch = Batch.objects.create(name="One-time campaign")
		BatchLead.objects.create(batch=batch, lead=self.lead, email=self.lead.email)

		response = self.client.post(
			f"/api/batches/{batch.pk}/send-now/",
			{"template": template.pk, "enquiry_date": "2026-10-22"},
			format="json",
		)

		self.assertEqual(response.status_code, 200, response.data)
		self.assertEqual(response.data, {"sent": 1, "failed": 0})
		batch.refresh_from_db()
		self.assertIsNotNone(batch.sequence_id)
		self.assertEqual(
			call_command_mock.call_args.kwargs["template_id"], template.pk
		)
		self.assertEqual(
			call_command_mock.call_args.kwargs["enquiry_date"], "2026-10-22"
		)

	@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
	@patch("campaigns.management.commands.process_email_campaign.save_to_sent")
	def test_send_enquiry_date_does_not_filter_campaign_recipients(self, _save_to_sent):
		from django.core import mail

		template = MessageTemplate.objects.create(
			name="Date-independent template",
			subject="Hello",
			body="Hello {{name}}, enquiry date {{enquiry_date}}.",
		)
		SequenceStep.objects.create(
			sequence=self.sequence,
			step_number=1,
			template=template,
		)
		self.lead.enquiry_date = date(2026, 10, 16)
		self.lead.save(update_fields=["enquiry_date"])
		other_lead = Lead.objects.create(
			name="Other recipient",
			email="other@example.com",
			enquiry_date=date(2026, 10, 19),
		)
		BatchLead.objects.create(
			batch=self.batch,
			lead=other_lead,
			email=other_lead.email,
		)

		response = self.client.post(
			f"/api/batches/{self.batch.pk}/send-now/",
			{"template": template.pk, "enquiry_date": "2026-10-22"},
			format="json",
		)

		self.assertEqual(response.status_code, 200, response.data)
		self.assertEqual(response.data["sent"], 2)
		self.assertEqual(len(mail.outbox), 2)
		self.assertTrue(all("2026-10-22" in message.body for message in mail.outbox))

	@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
	@patch("campaigns.management.commands.process_email_campaign.save_to_sent")
	def test_first_step_with_zero_delay_sends_immediately(self, _save_to_sent):
		template = MessageTemplate.objects.create(
			name="First step",
			subject="First",
			body="First email",
		)
		SequenceStep.objects.create(
			sequence=self.sequence,
			step_number=1,
			template=template,
			delay_days=0,
			delay_minutes=0,
		)

		call_command(
			"process_email_campaign",
			batch_id=self.batch.pk,
			batch_lead_id=self.batch_lead.pk,
			stdout=io.StringIO(),
		)

		from django.core import mail

		self.assertEqual(len(mail.outbox), 1)
		self.assertIn(
			f'href="{get_unsubscribe_url(self.batch_lead)}"',
			mail.outbox[0].body,
		)
		self.assertIn("unsubscribe here", mail.outbox[0].body)

	@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
	@patch("campaigns.management.commands.process_email_campaign.save_to_sent")
	def test_send_uses_current_lead_email_when_campaign_recipient_email_is_blank(
		self, _save_to_sent
	):
		from django.core import mail

		template = MessageTemplate.objects.create(
			name="Current lead email",
			subject="Hello",
			body="Hello there.",
		)
		SequenceStep.objects.create(
			sequence=self.sequence,
			step_number=1,
			template=template,
		)
		self.batch_lead.email = ""
		self.batch_lead.save(update_fields=["email"])

		call_command(
			"process_email_campaign",
			batch_id=self.batch.pk,
			batch_lead_id=self.batch_lead.pk,
			stdout=io.StringIO(),
		)

		self.assertEqual(len(mail.outbox), 1)
		self.assertEqual(mail.outbox[0].to, [self.lead.email])
		self.batch_lead.refresh_from_db()
		self.assertEqual(self.batch_lead.email, self.lead.email)

	@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
	@patch("campaigns.management.commands.process_email_campaign.save_to_sent")
	def test_first_step_respects_delay_minutes(self, _save_to_sent):
		template = MessageTemplate.objects.create(
			name="First step",
			subject="First",
			body="First email",
		)
		SequenceStep.objects.create(
			sequence=self.sequence,
			step_number=1,
			template=template,
			delay_days=0,
			delay_minutes=10,
		)

		call_command(
			"process_email_campaign",
			batch_id=self.batch.pk,
			batch_lead_id=self.batch_lead.pk,
			stdout=io.StringIO(),
		)

		from django.core import mail

		self.assertEqual(len(mail.outbox), 0)

	@override_settings(
		EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
		DEFAULT_FROM_EMAIL="CRM <sender@example.com>",
	)
	@patch("campaigns.management.commands.process_email_campaign.save_to_sent")
<<<<<<< HEAD
	def test_force_sends_next_step_using_global_reply_to(self, _save_to_sent):
=======
	def test_force_sends_next_step_using_campaign_reply_to(self, _save_to_sent):
>>>>>>> 612c1c9aa8f3fdd9f0332a8f1776fd6ed878a789
		first_template = MessageTemplate.objects.create(
			name="First step",
			subject="First",
			body="First email",
		)
		second_template = MessageTemplate.objects.create(
			name="Follow-up",
			subject="Follow-up",
			body="Follow-up email",
		)
		SequenceStep.objects.create(
			sequence=self.sequence,
			step_number=1,
			template=first_template,
		)
		SequenceStep.objects.create(
			sequence=self.sequence,
			step_number=2,
			template=second_template,
			delay_days=30,
		)
		self.batch_lead.current_step = 1
		self.batch_lead.last_email_sent_at = timezone.now()
		self.batch_lead.save(update_fields=["current_step", "last_email_sent_at"])
<<<<<<< HEAD
		EmailCampaignSettings.objects.create(
			reply_to_email="global-replies@example.com"
		)
=======
>>>>>>> 612c1c9aa8f3fdd9f0332a8f1776fd6ed878a789

		with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
			call_command(
				"process_email_campaign",
				batch_id=self.batch.pk,
				batch_lead_id=self.batch_lead.pk,
				force=True,
				stdout=io.StringIO(),
			)

		from django.core import mail

		self.assertEqual(len(mail.outbox), 1)
<<<<<<< HEAD
		self.assertEqual(
			mail.outbox[0].reply_to,
			["global-replies@example.com"],
		)
=======
		self.assertEqual(mail.outbox[0].reply_to, ["replies@example.com"])
>>>>>>> 612c1c9aa8f3fdd9f0332a8f1776fd6ed878a789
		self.batch_lead.refresh_from_db()
		self.assertEqual(self.batch_lead.current_step, 2)
		self.assertTrue(self.batch_lead.completed)


<<<<<<< HEAD
class EmailCampaignSettingsApiTests(TestCase):
	def setUp(self):
		user = get_user_model().objects.create_user(
			username="email-campaign-settings",
			email="email-campaign-settings@example.com",
			password="test-only-password",
		)
		self.client = APIClient()
		self.client.force_authenticate(user=user)

	def test_global_reply_to_is_saved_and_returned(self):
		response = self.client.patch(
			"/api/email-campaign-settings/",
			{"reply_to_email": "replies@example.com"},
			format="json",
		)

		self.assertEqual(response.status_code, 200, response.data)
		self.assertEqual(response.data["reply_to_email"], "replies@example.com")
		self.assertEqual(
			EmailCampaignSettings.objects.get(pk=1).reply_to_email,
			"replies@example.com",
		)

	def test_global_reply_to_rejects_invalid_email(self):
		response = self.client.patch(
			"/api/email-campaign-settings/",
			{"reply_to_email": "not-an-email"},
			format="json",
		)

		self.assertEqual(response.status_code, 400)


=======
>>>>>>> 612c1c9aa8f3fdd9f0332a8f1776fd6ed878a789
class FinalOfferGenerationTests(TestCase):
    def test_generate_final_offer_creates_pdf_and_updates_quotation(self):
        user = get_user_model().objects.create_user(
            username="finalofferuser",
            email="finaloffer@example.com",
            password="StrongPass123!",
        )
        country = Country.objects.create(name="India")
        state = State.objects.create(country=country, name="Gujarat")
        city = City.objects.create(state=state, name="Ahmedabad")
        company = Company.objects.create(
            name="Acme Components",
            city=city,
            state=state,
            country=country,
            gst_number="24AAAAA0000A1Z5",
        )
        opportunity = Opportunity.objects.create(
            company=company,
            project_name="Die Punch Tooling",
            enquiry_for="SALES",
            status="PROPOSAL_PRICE_QUOTE",
            assign_to=user,
        )
        quotation = Quotation.objects.create(
            quotation_number="QT-1001",
            quotation_date="2026-10-01",
            project_name="Die Punch Tooling",
            opportunity=opportunity,
            status="APPROVED",
            subtotal=Decimal("15000.00"),
            tax_percentage=Decimal("18.00"),
            tax_amount=Decimal("2700.00"),
            taxable_amount=Decimal("17700.00"),
            total_amount=Decimal("17700.00"),
            terms_conditions="Standard terms",
            delivery_timeline="15 days",
            created_by=user,
        )
        QuotationItem.objects.create(
            quotation=quotation,
            module_name="Die Punch Set",
            description="Tooling set",
            requirements="As per drawing",
            amount=Decimal("15000.00"),
        )

        client = APIClient()
        client.force_authenticate(user=user)

        response = client.post(f"/api/quotations/{quotation.id}/generate-final-offer/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["final_offer_generated"])
        self.assertTrue(response.data["final_offer_pdf"])

        quotation.refresh_from_db()
        self.assertTrue(quotation.final_offer_generated)
        self.assertTrue(quotation.final_offer_pdf.name)


class CpoCreationTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()
        self.user = get_user_model().objects.create_user(
            username="cpocreator",
            email="cpo@example.com",
            password="test-password",
        )
        self.quotation = Quotation.objects.create(
            quotation_number="QT-CPO-1001",
            quotation_date="2026-10-01",
            created_by=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def tearDown(self):
        self.media_override.disable()
        self.media_directory.cleanup()

    def test_mark_for_cpo_is_idempotent_and_does_not_create_po_details(self):
        url = f"/api/quotations/{self.quotation.id}/mark-for-cpo/"

        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["cpo_ready"], True)
        self.quotation.refresh_from_db()
        self.assertTrue(self.quotation.cpo_ready)
        self.assertEqual(self.quotation.customer_po_number, "")
        self.assertFalse(self.quotation.customer_po_document)

        repeated_response = self.client.post(url)

        self.assertEqual(repeated_response.status_code, 200)
        self.assertIn("already marked", repeated_response.data["message"])
        self.assertEqual(Quotation.objects.filter(cpo_ready=True).count(), 1)

    def test_mark_for_cpo_requires_authentication(self):
        client = APIClient()

        response = client.post(f"/api/quotations/{self.quotation.id}/mark-for-cpo/")

        self.assertEqual(response.status_code, 401)
        self.quotation.refresh_from_db()
        self.assertFalse(self.quotation.cpo_ready)

    def test_mark_for_cpo_returns_not_found_for_missing_quotation(self):
        response = self.client.post("/api/quotations/999999/mark-for-cpo/")

        self.assertEqual(response.status_code, 404)

    def test_cpo_list_only_contains_marked_quotations(self):
        unmarked = Quotation.objects.create(
            quotation_number="QT-CPO-UNMARKED",
            quotation_date="2026-10-01",
            created_by=self.user,
        )
        self.client.post(f"/api/quotations/{self.quotation.id}/mark-for-cpo/")

        response = self.client.get("/api/cpos/")

        self.assertEqual(response.status_code, 200)
        listed_ids = {item["id"] for item in response.data}
        self.assertIn(self.quotation.id, listed_ids)
        self.assertNotIn(unmarked.id, listed_ids)

    def test_customer_po_upload_saves_document_and_requires_manual_number_review(self):
        self.client.post(f"/api/quotations/{self.quotation.id}/mark-for-cpo/")
        document = SimpleUploadedFile(
            "customer-po.pdf",
            b"%PDF-1.4 customer order",
            content_type="application/pdf",
        )

        response = self.client.post(
            f"/api/quotations/{self.quotation.id}/customer-po/",
            {"customer_po_document": document},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["manual_review_required"])
        self.quotation.refresh_from_db()
        self.assertTrue(self.quotation.customer_po_document.name)
        self.assertEqual(self.quotation.customer_po_number, "")
        self.assertIn("review it manually", response.data["message"])

    def test_customer_po_upload_accepts_number_and_replaces_document(self):
        self.client.post(f"/api/quotations/{self.quotation.id}/mark-for-cpo/")
        first_response = self.client.post(
            f"/api/quotations/{self.quotation.id}/customer-po/",
            {
                "customer_po_document": SimpleUploadedFile(
                    "first.pdf", b"%PDF-1.4 first", content_type="application/pdf"
                ),
                "customer_po_number": "PO-100",
            },
            format="multipart",
        )
        self.assertEqual(first_response.status_code, 200, first_response.data)
        self.quotation.refresh_from_db()
        first_document_name = self.quotation.customer_po_document.name

        response = self.client.post(
            f"/api/quotations/{self.quotation.id}/customer-po/",
            {
                "customer_po_document": SimpleUploadedFile(
                    "replacement.pdf",
                    b"%PDF-1.4 replacement",
                    content_type="application/pdf",
                ),
                "customer_po_number": "PO-200",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["manual_review_required"])
        self.quotation.refresh_from_db()
        self.assertEqual(self.quotation.customer_po_number, "PO-200")
        self.assertNotEqual(self.quotation.customer_po_document.name, first_document_name)

    def test_customer_po_upload_rejects_missing_or_invalid_document(self):
        self.client.post(f"/api/quotations/{self.quotation.id}/mark-for-cpo/")

        missing_response = self.client.post(
            f"/api/quotations/{self.quotation.id}/customer-po/",
            {},
            format="multipart",
        )
        invalid_response = self.client.post(
            f"/api/quotations/{self.quotation.id}/customer-po/",
            {
                "customer_po_document": SimpleUploadedFile(
                    "not-a-pdf.pdf",
                    b"not a pdf",
                    content_type="application/pdf",
                )
            },
            format="multipart",
        )

        self.assertEqual(missing_response.status_code, 400)
        self.assertEqual(invalid_response.status_code, 400)
        self.quotation.refresh_from_db()
        self.assertFalse(self.quotation.customer_po_document)

    def test_customer_po_upload_rejects_unmarked_quotation(self):
        response = self.client.post(
            f"/api/quotations/{self.quotation.id}/customer-po/",
            {
                "customer_po_document": SimpleUploadedFile(
                    "customer-po.pdf", b"%PDF-1.4 content", content_type="application/pdf"
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.quotation.refresh_from_db()
        self.assertFalse(self.quotation.customer_po_document)


class LeadSerializerTests(TestCase):
    def test_company_master_names_are_resolved_to_model_instances(self):
        country = Country.objects.create(name="India")
        state = State.objects.create(country=country, name="Gujarat")
        city = City.objects.create(state=state, name="Ahemdabad")

        lead = LeadSerializer().create(
            {
                "company_name": "Acme Labs",
                "company_address": "MG Road",
                "company_city": "Ahemdabad",
                "company_state": "Gujarat",
                "company_country": "India",
                "company_pincode": "380001",
                "company_gst_number": "GST-123",
                "contact_name": "Nitin Shah",
                "contact_designation": "Manager",
                "contact_mobile": "9999999999",
                "contact_email": "nitin@example.com",
                "enquiry_for": "LEAD",
                "enquiry_date": "2026-09-30",
                "source": "WEBSITE",
                "status": "NEW",
            }
        )

        self.assertEqual(lead.company.name, "Acme Labs")
        self.assertEqual(lead.company.city, city)
        self.assertEqual(lead.company.state, state)
        self.assertEqual(lead.company.country, country)
        self.assertTrue(CompanyContact.objects.filter(company=lead.company, name="Nitin Shah").exists())

    def test_enquiry_for_options_include_project_names(self):
        client = APIClient()
        user = get_user_model().objects.create_user(
            username="optionsreader",
            email="optionsreader@example.com",
            password="StrongPass123!",
        )
        client.force_authenticate(user=user)

        response = client.get("/api/lead-options/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn({"value": "CRM", "label": "CRM Software"}, response.data["enquiry_for"])
        self.assertIn({"value": "EMAIL", "label": "Email Campaign"}, response.data["enquiry_for"])
        self.assertIn({"value": "WHATSAPP", "label": "WhatsApp Campaign"}, response.data["enquiry_for"])
        self.assertIn({"value": "SALES", "label": "Sales Automation"}, response.data["enquiry_for"])

    def test_csv_import_creates_related_masters(self):
        client = APIClient()
        user = get_user_model().objects.create_user(
            username="importer",
            email="importer@example.com",
            password="StrongPass123!",
        )
        client.force_authenticate(user=user)

        csv_buffer = io.StringIO()
        writer = csv.DictWriter(
            csv_buffer,
            fieldnames=[
                "company_name",
                "company_address",
                "company_city",
                "company_state",
                "company_pincode",
                "company_country",
                "company_gst_number",
                "contact_name",
                "contact_designation",
                "contact_mobile",
                "contact_email",
                "enquiry_for",
                "enquiry_date",
                "source",
                "status",
                "followup_date",
                "followup_remarks",
                "is_opportunity",
            ],
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "company_name": "Acme Labs",
                    "company_address": "MG Road",
                    "company_city": "Ahmedabad",
                    "company_state": "Gujarat",
                    "company_pincode": "380001",
                    "company_country": "India",
                    "company_gst_number": "GST-123",
                    "contact_name": "Nitin Shah",
                    "contact_designation": "Manager",
                    "contact_mobile": "9999999999",
                    "contact_email": "nitin@example.com",
                    "enquiry_for": "LEAD",
                    "enquiry_date": "2026-09-30",
                    "source": "WEBSITE",
                    "status": "NEW",
                    "followup_date": "",
                    "followup_remarks": "",
                    "is_opportunity": "false",
                },
                {
                    "company_name": "Nova Power",
                    "company_address": "Powai",
                    "company_city": "Mumbai",
                    "company_state": "Maharashtra",
                    "company_pincode": "400076",
                    "company_country": "India",
                    "company_gst_number": "GST-456",
                    "contact_name": "Priya Nair",
                    "contact_designation": "Sales Head",
                    "contact_mobile": "9876543210",
                    "contact_email": "priya@example.com",
                    "enquiry_for": "CLIENT",
                    "enquiry_date": "2026-10-01",
                    "source": "REFERENCE",
                    "status": "HOT",
                    "followup_date": "2026-10-05",
                    "followup_remarks": "Follow-up scheduled",
                    "is_opportunity": "true",
                },
            ]
        )

        response = client.post(
            "/api/leads/import-csv/",
            {
                "file": SimpleUploadedFile(
                    "leads.csv",
                    csv_buffer.getvalue().encode("utf-8"),
                    content_type="text/csv",
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Lead.objects.count(), 2)
        self.assertTrue(Country.objects.filter(name="India").exists())
        self.assertTrue(State.objects.filter(name="Gujarat").exists())
        self.assertTrue(State.objects.filter(name="Maharashtra").exists())
        self.assertTrue(City.objects.filter(name="Ahmedabad").exists())
        self.assertTrue(City.objects.filter(name="Mumbai").exists())
        self.assertTrue(Company.objects.filter(name="Acme Labs").exists())
        self.assertTrue(Company.objects.filter(name="Nova Power").exists())
        self.assertTrue(CompanyContact.objects.filter(name="Nitin Shah").exists())
        self.assertTrue(CompanyContact.objects.filter(name="Priya Nair").exists())

    def test_csv_import_accepts_missing_columns_and_values(self):
        client = APIClient()
        user = get_user_model().objects.create_user(
            username="partialimporter",
            email="partialimporter@example.com",
            password="test-password",
        )
        client.force_authenticate(user=user)

        response = client.post(
            "/api/leads/import-csv/",
            {
                "file": SimpleUploadedFile(
                    "partial-leads.csv",
                    (
                        b"company_name,contact_name,followup_remarks\n"
                        b"Acme Labs,,\n"
                        b",,Needs company lookup\n"
                    ),
                    content_type="text/csv",
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["imported"], 2)
        self.assertEqual(response.data["invalid"], 0)
        lead = Lead.objects.get(company__name="Acme Labs")
        self.assertEqual(lead.company.name, "Acme Labs")
        self.assertEqual(lead.enquiry_date, timezone.localdate())
        self.assertEqual(lead.source, "OTHER")
        self.assertEqual(lead.status, "OTHER")
        standalone_lead = Lead.objects.get(company__isnull=True)
        self.assertEqual(standalone_lead.followup_remarks, "Needs company lookup")
        self.assertEqual(standalone_lead.enquiry_date, timezone.localdate())

    def test_csv_import_detects_tab_delimited_file(self):
        client = APIClient()
        user = get_user_model().objects.create_user(
            username="tabimporter",
            email="tabimporter@example.com",
            password="test-password",
        )
        client.force_authenticate(user=user)

        response = client.post(
            "/api/leads/import-csv/",
            {
                "file": SimpleUploadedFile(
                    "tab-leads.csv",
                    (
                        "company_name\tcontact_email\tcontact_mobile\n"
                        "Testting\tTEST@GMAIL.COM\t1234567890\n"
                    ).encode("utf-8"),
                    content_type="text/csv",
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["imported"], 1)
        lead = Lead.objects.get(company__name="Testting")
        self.assertIsNone(lead.contact)
        self.assertEqual(lead.email, "TEST@GMAIL.COM")
        self.assertEqual(lead.phone, "1234567890")
        self.assertEqual(lead.enquiry_date, timezone.localdate())

    def test_csv_import_accepts_day_month_year_dates_and_defaults_unknown_values(self):
        client = APIClient()
        user = get_user_model().objects.create_user(
            username="datedimporter",
            email="datedimporter@example.com",
            password="test-password",
        )
        client.force_authenticate(user=user)

        response = client.post(
            "/api/leads/import-csv/",
            {
                "file": SimpleUploadedFile(
                    "dated-leads.csv",
                    (
                        b"company_name,enquiry_date,source,status,followup_date\n"
                        b"Acme,22-10-2026,OTHER,Active,11-11-2026\n"
                        b"Beta,22-10-2026,test,Active,11-11-2026\n"
                    ),
                    content_type="text/csv",
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["imported"], 2)
        self.assertEqual(response.data["invalid"], 0)
        self.assertEqual(response.data["row_errors"], [])
        lead = Lead.objects.get(company__name="Acme")
        self.assertEqual(str(lead.enquiry_date), "2026-10-22")
        self.assertEqual(str(lead.followup_date), "2026-11-11")
        self.assertEqual(lead.status, "ACTIVE")
        unknown_source_lead = Lead.objects.get(company__name="Beta")
        self.assertEqual(unknown_source_lead.source, "OTHER")
        self.assertEqual(unknown_source_lead.status, "ACTIVE")

    def test_xlsx_import_accepts_excel_dates_and_defaults_blank_source_and_status(self):
        from openpyxl import Workbook

        client = APIClient()
        user = get_user_model().objects.create_user(
            username="excelimporter",
            email="excelimporter@example.com",
            password="test-password",
        )
        client.force_authenticate(user=user)

        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["company_name", "enquiry_date", "followup_date", "source", "status"])
        sheet.append(["Excel Company", date(2026, 10, 22), date(2026, 11, 11), "", ""])
        excel_file = io.BytesIO()
        workbook.save(excel_file)

        response = client.post(
            "/api/leads/import-csv/",
            {
                "file": SimpleUploadedFile(
                    "leads.xlsx",
                    excel_file.getvalue(),
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["imported"], 1)
        lead = Lead.objects.get(company__name="Excel Company")
        self.assertEqual(str(lead.enquiry_date), "2026-10-22")
        self.assertEqual(str(lead.followup_date), "2026-11-11")
        self.assertEqual(lead.source, "OTHER")
        self.assertEqual(lead.status, "OTHER")


class OpportunityConversionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="salesrep",
            email="sales@example.com",
            password="strong-pass-123",
        )
        self.client.force_authenticate(user=self.user)

        self.company = Company.objects.create(name="ABC Technologies")
        self.opportunity = Opportunity.objects.create(
            company=self.company,
            project_name="Inventory Management System",
            enquiry_for="CLIENT",
            status="PROSPECTING",
            is_active=True,
        )
        self.module_1 = OpportunityModule.objects.create(
            opportunity=self.opportunity,
            module_number=1,
            module_name="Product Management",
            description="Product & category management",
            estimated_cost=Decimal("40000"),
        )
        self.module_2 = OpportunityModule.objects.create(
            opportunity=self.opportunity,
            module_number=2,
            module_name="Inventory Management",
            description="Stock management",
            estimated_cost=Decimal("35000"),
        )

    def test_converts_opportunity_with_user_submitted_module_amounts(self):
        payload = {
            "items": [
                {"module": self.module_1.id, "amount": "40000"},
                {"module": self.module_2.id, "amount": "45000"},
            ]
        }

        response = self.client.post(
            f"/api/opportunities/{self.opportunity.id}/convert-to-quotation/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Quotation.objects.count(), 1)
        quotation = Quotation.objects.get()
        self.assertEqual(quotation.project_name, "Inventory Management System")
        self.assertEqual(quotation.subtotal, Decimal("85000.00"))
        self.assertEqual(quotation.total_amount, Decimal("85000.00"))
        self.assertEqual(quotation.items.count(), 2)
        self.assertEqual(quotation.items.get(module=self.module_1).amount, Decimal("40000.00"))
        self.assertEqual(quotation.items.get(module=self.module_2).amount, Decimal("45000.00"))
        self.assertEqual(response.data["quotation"]["project_name"], "Inventory Management System")


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

	def test_creates_campaign_without_sequence(self):
		user = get_user_model().objects.create_user(
			username="campaign-without-sequence",
			email="campaign-without-sequence@example.com",
			password="test-password",
		)
		self.client.force_authenticate(user=user)
		response = self.client.post(
			"/api/batches/",
			{
				"name": "One-time campaign",
				"lead_ids": [self.lead.sr_no],
			},
			format="json",
		)

		self.assertEqual(response.status_code, 201, response.data)
		self.assertIsNone(response.data["sequence"])
		self.assertTrue(
			BatchLead.objects.filter(
				batch_id=response.data["id"],
				lead=self.lead,
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


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CampaignAutomaticProcessingTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(
			username="automatic-campaign-user",
			email="automatic-campaign@example.com",
			password="automatic-campaign-test-password",
		)
		self.client = APIClient()
		self.client.force_authenticate(user=self.user)
		self.template = MessageTemplate.objects.create(
			name="Immediate welcome",
			subject="Welcome",
			body="Welcome aboard.",
		)
		self.sequence = Sequence.objects.create(name="Immediate welcome sequence")
		self.step = SequenceStep.objects.create(
			sequence=self.sequence,
			step_number=1,
			template=self.template,
			delay_days=0,
			delay_minutes=0,
		)
		self.lead = Lead.objects.create(
			name="Immediate recipient",
			email="immediate@example.com",
		)

	def create_campaign(self, *, status_value=Batch.Status.ACTIVE, lead_ids=None):
		return self.client.post(
			"/api/batches/",
			{
				"name": "Immediate campaign",
				"sequence": self.sequence.pk,
				"lead_ids": [self.lead.pk] if lead_ids is None else lead_ids,
				"status": status_value,
			},
			format="json",
		)

	@patch("campaigns.management.commands.process_email_campaign.save_to_sent")
	def test_campaign_creation_sends_after_batch_leads_are_saved(self, _save_to_sent):
		from django.core import mail

		with self.captureOnCommitCallbacks(execute=True) as callbacks:
			response = self.create_campaign()

		self.assertEqual(response.status_code, 201, response.data)
		self.assertEqual(len(callbacks), 1)
		batch_lead = BatchLead.objects.get(batch_id=response.data["id"])
		self.assertEqual(batch_lead.email, self.lead.email)
		self.assertEqual(len(mail.outbox), 1)
		self.assertEqual(mail.outbox[0].to, [self.lead.email])
		self.assertEqual(batch_lead.current_step, 1)

	@patch("campaigns.management.commands.process_email_campaign.save_to_sent")
	def test_resume_sends_immediate_first_step(self, _save_to_sent):
		from django.core import mail

		with self.captureOnCommitCallbacks(execute=True):
			response = self.create_campaign(status_value=Batch.Status.PAUSED)
		self.assertEqual(response.status_code, 201, response.data)
		self.assertEqual(mail.outbox, [])

		with self.captureOnCommitCallbacks(execute=True) as callbacks:
			resume_response = self.client.patch(
				f"/api/batches/{response.data['id']}/resume/"
			)

		self.assertEqual(resume_response.status_code, 200, resume_response.data)
		self.assertEqual(len(callbacks), 1)
		self.assertEqual(len(mail.outbox), 1)

	@patch("campaigns.management.commands.process_email_campaign.save_to_sent")
	def test_campaign_creation_does_not_send_before_nonzero_first_step_delay(
		self, _save_to_sent
	):
		from django.core import mail

		self.step.delay_minutes = 10
		self.step.save(update_fields=["delay_minutes"])

		with self.captureOnCommitCallbacks(execute=True):
			response = self.create_campaign()

		self.assertEqual(response.status_code, 201, response.data)
		self.assertTrue(BatchLead.objects.filter(batch_id=response.data["id"]).exists())
		self.assertEqual(mail.outbox, [])

	@patch("campaigns.management.commands.process_email_campaign.save_to_sent")
	def test_campaign_without_recipients_is_logged_and_sends_nothing(
		self, _save_to_sent
	):
		from django.core import mail

		with self.assertLogs(
			"campaigns.management.commands.process_email_campaign", level="WARNING"
		):
			with self.captureOnCommitCallbacks(execute=True):
				response = self.create_campaign(lead_ids=[])

		self.assertEqual(response.status_code, 201, response.data)
		self.assertFalse(BatchLead.objects.filter(batch_id=response.data["id"]).exists())
		self.assertEqual(mail.outbox, [])

	@patch("campaigns.management.commands.process_email_campaign.save_to_sent")
	def test_reprocessing_does_not_send_a_completed_first_step_twice(self, _save_to_sent):
		from django.core import mail

		with self.captureOnCommitCallbacks(execute=True):
			response = self.create_campaign()
		self.assertEqual(response.status_code, 201, response.data)
		call_command("process_email_campaign", batch_id=response.data["id"])
		self.assertEqual(len(mail.outbox), 1)


class OrderDashboardAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="order-dashboard-user",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_returns_commercial_stage_totals_and_monthly_history(self):
        company = Company.objects.create(name="Dashboard Company")
        quotation = Quotation.objects.create(
            quotation_number="QT-DASH-1001",
            quotation_date="2026-04-15",
            created_by=self.user,
            final_offer_generated=True,
            cpo_created=True,
            cpo_date="2026-04-20",
            total_amount=Decimal("1180.00"),
        )
        Quotation.objects.create(
            quotation_number="QT-DASH-1002",
            quotation_date="2026-05-10",
            created_by=self.user,
            total_amount=Decimal("590.00"),
        )
        SalesOrder.objects.create(
            so_number="SO-DASH-1001",
            so_date="2026-04-25",
            quotation=quotation,
            company=company,
            total_amount=Decimal("1180.00"),
            created_by=self.user,
        )

        response = self.client.get(
            "/api/order-dashboard/",
            {
                "period": "custom",
                "start_date": "2026-04-01",
                "end_date": "2026-05-31",
            },
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["summary"]["total_quotations"], 2)
        self.assertEqual(response.data["summary"]["quotations_amount"], 1770.0)
        self.assertEqual(response.data["summary"]["fo_generated"], 1)
        self.assertEqual(response.data["summary"]["cpo_received"], 1)
        self.assertEqual(response.data["summary"]["total_so"], 1)
        self.assertEqual(len(response.data["monthly_history"]), 2)
        self.assertEqual(response.data["monthly_history"][0]["month"], "Apr 2026")
        self.assertEqual(response.data["monthly_history"][0]["quotations"], 1)
        self.assertEqual(response.data["monthly_history"][0]["fo"], 1)
        self.assertEqual(response.data["monthly_history"][0]["cpo"], 1)
        self.assertEqual(response.data["monthly_history"][0]["so"], 1)

    def test_rejects_invalid_order_dashboard_period(self):
        response = self.client.get(
            "/api/order-dashboard/", {"period": "daily", "year": "2026"}
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.get(
            "/api/order-dashboard/",
            {
                "period": "custom",
                "start_date": "2026-06-01",
                "end_date": "2026-05-01",
            },
        )
        self.assertEqual(response.status_code, 400)


class TaskActivitiesAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="activity-user",
            password="StrongPass123!",
        )
        self.other_user = get_user_model().objects.create_user(
            username="other-activity-user",
            password="StrongPass123!",
        )
        self.client.force_authenticate(user=self.user)
        self.today = timezone.localdate()

    def create_task(self, title, followup_date, status="PENDING", **kwargs):
        task_regarding = kwargs.pop("task_regarding", "MISCELLANEOUS")
        reference_id = kwargs.pop(
            "reference_id",
            "" if task_regarding.upper() == "MISCELLANEOUS" else "test-reference",
        )
        return Task.objects.create(
            title=title,
            module="LEAD",
            task_regarding=task_regarding,
            reference_id=reference_id,
            followup_date=followup_date,
            status=status,
            created_by=self.user,
            **kwargs,
        )

    def test_returns_task_groups_and_hides_other_users_tasks(self):
        today_task = self.create_task("Today", self.today, assigned_to=self.user)
        upcoming_task = self.create_task("Upcoming", self.today + timedelta(days=3))
        overdue_task = self.create_task(
            "Overdue",
            self.today - timedelta(days=1),
            status="IN_PROGRESS",
            assigned_to=self.user,
        )
        recurring_task = self.create_task(
            "Recurring",
            self.today + timedelta(days=30),
            status="COMPLETED",
            is_recurring=True,
        )
        hidden_task = Task.objects.create(
            title="Private task",
            module="LEAD",
            task_regarding="MISCELLANEOUS",
            followup_date=self.today,
            status="PENDING",
            created_by=self.other_user,
            assigned_to=self.other_user,
        )

        response = self.client.get("/api/tasks/activities/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["today"]["count"], 1)
        self.assertEqual(response.data["today"]["tasks"][0]["id"], today_task.id)
        self.assertEqual(response.data["upcoming"]["count"], 1)
        self.assertEqual(response.data["upcoming"]["tasks"][0]["id"], upcoming_task.id)
        self.assertEqual(response.data["overdue"]["count"], 1)
        self.assertEqual(response.data["overdue"]["tasks"][0]["id"], overdue_task.id)
        self.assertEqual(response.data["recurring"]["count"], 1)
        self.assertEqual(response.data["recurring"]["tasks"][0]["id"], recurring_task.id)
        self.assertNotIn(hidden_task.id, [
            task["id"]
            for group in response.data.values()
            for task in group["tasks"]
        ])

    def test_followup_change_records_previous_date_and_remark(self):
        previous_date = self.today - timedelta(days=2)
        task = self.create_task(
            "Follow up",
            previous_date,
            remarks="Call the customer",
        )

        response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {
                "followup_date": str(self.today),
                "remarks": "New reminder for next week",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["followup_date"], str(self.today))
        self.assertEqual(len(response.data["followup_history"]), 1)
        history_entry = response.data["followup_history"][0]
        self.assertEqual(history_entry["followup_date"], str(previous_date))
        self.assertEqual(history_entry["remark"], "Call the customer")
        self.assertEqual(history_entry["updated_by"], self.user.get_username())
        self.assertTrue(history_entry["timestamp"])

    def test_edit_without_followup_date_change_does_not_add_history(self):
        task = self.create_task("Follow up", self.today)

        response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"remarks": "Updated task detail"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["followup_history"], [])

    def test_dashboard_returns_aggregates_for_visible_tasks(self):
        self.create_task(
            "Miscellaneous",
            self.today,
            status="PENDING",
            task_regarding="MISCELLANEOUS",
            assigned_to=self.user,
            priority="HIGH",
            is_recurring=True,
        )
        self.create_task(
            "Overdue",
            self.today - timedelta(days=1),
            status="IN_PROGRESS",
            task_regarding="Payment",
            assigned_to=self.user,
            priority="MEDIUM",
        )
        self.create_task(
            "Completed",
            self.today + timedelta(days=1),
            status="COMPLETED",
            task_regarding="Follow Up",
            assigned_to=self.user,
            priority="LOW",
        )
        Task.objects.create(
            title="Private task",
            module="LEAD",
            task_regarding="MISCELLANEOUS",
            followup_date=self.today,
            status="PENDING",
            created_by=self.other_user,
            assigned_to=self.other_user,
        )

        response = self.client.get("/api/tasks/dashboard/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total"], 3)
        self.assertEqual(
            {row["status"]: row["count"] for row in response.data["by_status"]},
            {"COMPLETED": 1, "IN_PROGRESS": 1, "PENDING": 1},
        )
        self.assertEqual(
            {row["priority"]: row["count"] for row in response.data["by_priority"]},
            {"HIGH": 1, "LOW": 1, "MEDIUM": 1},
        )
        self.assertEqual(
            {row["module"]: row["count"] for row in response.data["by_module"]},
            {"LEAD": 3},
        )
        self.assertEqual(response.data["in_progress"], 1)
        self.assertEqual(response.data["pending"], 1)
        self.assertEqual(response.data["recurring"], 1)
        self.assertEqual(response.data["overdue"], 1)
        self.assertEqual(response.data["due_today"], 1)
        self.assertEqual(response.data["upcoming"], 0)
        self.assertEqual(response.data["miscellaneous"], 1)
        self.assertEqual(response.data["completed"], 1)

    def test_dashboard_filters_assignee_without_loading_a_user_model(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        Task.objects.create(
            title="Other user's task",
            module="LEAD",
            task_regarding="MISCELLANEOUS",
            followup_date=self.today,
            status="PENDING",
            created_by=self.other_user,
            assigned_to=self.other_user,
        )

        response = self.client.get(
            "/api/tasks/dashboard/", {"user_id": self.other_user.pk}
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total"], 1)

        invalid_response = self.client.get(
            "/api/tasks/dashboard/", {"user_id": "not-a-valid-id"}
        )
        self.assertEqual(invalid_response.status_code, 400)

    def test_recurring_command_creates_due_child_once_with_parent_details(self):
        today = date(2026, 10, 6)
        parent = self.create_task(
            "Call customer",
            today - timedelta(days=1),
            assigned_to=self.user,
            remarks="Use updated contact details",
            is_recurring=True,
            repeat_frequency="DAILY",
            repeat_interval=1,
            repeat_end_date=today + timedelta(days=2),
        )

        with patch(
            "campaigns.management.commands.create_recurring_tasks.timezone.localdate",
            return_value=today,
        ):
            output = io.StringIO()
            call_command("create_recurring_tasks", stdout=output)
            call_command("create_recurring_tasks", stdout=io.StringIO())

        instances = Task.objects.filter(parent_task=parent)
        self.assertEqual(instances.count(), 1)
        instance = instances.get()
        self.assertEqual(instance.followup_date, today)
        self.assertEqual(instance.status, "PENDING")
        self.assertFalse(instance.is_recurring)
        self.assertEqual(instance.assigned_to, self.user)
        self.assertEqual(instance.remarks, "Use updated contact details")
        self.assertIn("Total created: 1", output.getvalue())

    def test_recurring_command_respects_repeat_end_date_and_monthly_clamping(self):
        from campaigns.management.commands.create_recurring_tasks import Command

        today = date(2026, 3, 1)
        expired_parent = self.create_task(
            "Expired",
            today - timedelta(days=1),
            is_recurring=True,
            repeat_frequency="DAILY",
            repeat_interval=1,
            repeat_end_date=today - timedelta(days=1),
        )
        monthly_parent = self.create_task(
            "Monthly",
            date(2026, 1, 31),
            is_recurring=True,
            repeat_frequency="MONTHLY",
            repeat_interval=1,
        )
        leap_year_parent = self.create_task(
            "Leap year",
            date(2024, 2, 29),
            is_recurring=True,
            repeat_frequency="YEARLY",
            repeat_interval=1,
        )

        with patch(
            "campaigns.management.commands.create_recurring_tasks.timezone.localdate",
            return_value=today,
        ):
            call_command("create_recurring_tasks", stdout=io.StringIO())

        self.assertFalse(Task.objects.filter(parent_task=expired_parent).exists())
        monthly_instance = Task.objects.get(parent_task=monthly_parent)
        self.assertEqual(monthly_instance.followup_date, date(2026, 2, 28))
        self.assertEqual(
            Command.get_next_date(leap_year_parent.followup_date, leap_year_parent),
            date(2025, 2, 28),
        )