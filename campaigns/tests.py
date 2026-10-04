import csv
import io
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from .models import (
    Batch,
    BatchLead,
    Channel,
    City,
    Company,
    CompanyContact,
    Country,
    Lead,
    MessageTemplate,
    Opportunity,
    OpportunityModule,
    Quotation,
    QuotationItem,
    Sequence,
    State,
)
from .serializers import LeadSerializer


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

	def test_allows_whatsapp_only_lead_with_opt_in(self):
		lead = Lead.objects.create(
			name="Asha Example",
			company="Example Co",
			phone="+919876543210",
			whatsapp_opt_in=True,
		)

		self.assertIsNone(lead.email)
		self.assertTrue(lead.whatsapp_opt_in)