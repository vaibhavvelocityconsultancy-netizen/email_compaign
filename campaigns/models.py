from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import models


# Create your models here.
class Company(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=200)
    is_contact = models.BooleanField(default=False)
    address = models.TextField(blank=True)
    city = models.ForeignKey("City", on_delete=models.SET_NULL, null=True, blank=True)
    state = models.ForeignKey("State", on_delete=models.SET_NULL, null=True, blank=True)
    pincode = models.CharField(max_length=10, blank=True)
    country = models.ForeignKey(
        "Country", on_delete=models.CASCADE, null=True, blank=True
    )
    gst_number = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class CompanyContact(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="contacts"
    )
    name = models.CharField(max_length=100)
    designation = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.company.is_contact:
            self.company.is_contact = True
            self.company.save(update_fields=["is_contact"])

    def __str__(self):
        return f"{self.name} - {self.company.name}"


class Country(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class State(models.Model):
    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, related_name="states"
    )
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["country", "name"], name="unique_state_per_country"
            )
        ]

    def __str__(self):
        return f"{self.name}, {self.country.name}"


class City(models.Model):
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="cities")
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["state", "name"], name="unique_city_per_state"
            )
        ]

    def __str__(self):
        return f"{self.name}, {self.state.name}"


class Channel(models.TextChoices):
    EMAIL = "email", "Email"
    WHATSAPP = "whatsapp", "WhatsApp"


class Lead(models.Model):
    ENQUIRY_FOR_CHOICES = [
        ("LEAD", "Lead"),
        ("CLIENT", "Client"),
        ("CRM", "CRM Software"),
        ("EMAIL", "Email Campaign"),
        ("WHATSAPP", "WhatsApp Campaign"),
        ("SALES", "Sales Automation"),
        ("MARKETING", "Marketing Solution"),
        ("CUSTOM", "Custom Project"),
    ]
    SOURCE_CHOICES = [
        ("WEBSITE", "Website"),
        ("SOCIAL_MEDIA", "Social Media"),
        ("GOOGLE", "Google Search"),
        ("ADVERTISEMENT", "Advertisement"),
        ("REFERENCE", "Reference"),
        ("EXISTING_CLIENT", "Existing Client"),
        ("COLD_CALL", "Cold Call"),
        ("EMAIL_MARKETING", "Email Marketing"),
        ("OTHER", "Other"),
    ]

    STATUS_CHOICES = [
        ("NEW", "New"),
        ("ACTIVE", "Active"),
        ("JUNK", "Junk"),
        ("HOT", "Hot"),
        ("COLD", "Cold"),
        ("OTHER", "Other"),
    ]

    # Compatibility fields used by older tests and simpler lead creation flows.
    name = models.CharField(max_length=200, blank=True, default="")
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, default="")
    whatsapp_opt_in = models.BooleanField(default=False)

    # Basic info
    sr_no = models.AutoField(primary_key=True)
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="leads", null=True, blank=True
    )
    contact = models.ForeignKey(
        CompanyContact,
        on_delete=models.SET_NULL,
        related_name="leads",
        null=True,
        blank=True,
    )
    enquiry_for = models.CharField(max_length=20, choices=ENQUIRY_FOR_CHOICES, blank=True, default="LEAD")

    # Enquirey details
    enquiry_date = models.DateField(null=True, blank=True)
    # lead_received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='received_enquiries')
    # lead_assign_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_leads')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, blank=True, default="OTHER")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="NEW")
    followup_date = models.DateField(null=True, blank=True)
    followup_remarks = models.TextField(blank=True)

    # Audit
    tracker = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    is_opportunity = models.BooleanField(default=False)
    followup_history = models.JSONField(default=list, blank=True)

    def __init__(self, *args, **kwargs):
        company_value = kwargs.get("company")
        if isinstance(company_value, str):
            kwargs["company"] = self._resolve_company_name(company_value)
        super().__init__(*args, **kwargs)
        if isinstance(self.company, str):
            self.company = self._resolve_company_name(self.company)

    @staticmethod
    def _resolve_company_name(company_name):
        if not company_name:
            return None
        company = Company.objects.filter(name__iexact=company_name).first()
        if company is not None:
            return company
        return Company.objects.create(name=company_name)

    def save(self, *args, **kwargs):
        if isinstance(self.company, str):
            self.company = self._resolve_company_name(self.company)
        if not self.name and self.company and self.company.name:
            self.name = self.company.name
        if self.email in (None, ""):
            self.email = None
        if not self.phone and self.contact and self.contact.phone:
            self.phone = self.contact.phone
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name or f"Enquiry #{self.sr_no}"


class MessageTemplate(models.Model):
    channel = models.CharField(
        max_length=20, choices=Channel.choices, default=Channel.EMAIL
    )
    name = models.CharField(max_length=255)
    subject = models.CharField(max_length=500, blank=True)
    body = models.TextField()
    signature = models.TextField(blank=True)
    logo = models.ImageField(upload_to="email_logos/", null=True, blank=True)
    attachment = models.FileField(upload_to="email_attachments/", null=True, blank=True)
    wa_template_name = models.CharField(max_length=255, blank=True)
    wa_language = models.CharField(max_length=10, blank=True, default="en")
    wa_status = models.CharField(max_length=20, blank=True)
    # created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):

        return self.name


class Sequence(models.Model):
    channel = models.CharField(
        max_length=20, choices=Channel.choices, default=Channel.EMAIL
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class SequenceStep(models.Model):
    sequence = models.ForeignKey(
        Sequence, on_delete=models.CASCADE, related_name="steps"
    )
    step_number = models.PositiveIntegerField()
    template = models.ForeignKey(MessageTemplate, on_delete=models.CASCADE)
    delay_days = models.PositiveIntegerField(default=0)
    delay_minutes = models.IntegerField(default=0)

    class Meta:
        ordering = ["step_number"]
        unique_together = ["sequence", "step_number"]

    def __str__(self):
        return f"{self.sequence.name} - Step {self.step_number}"

    def clean(self):
        if (
            self.sequence_id
            and self.template_id
            and self.sequence.channel != self.template.channel
        ):
            raise ValidationError(
                {"template": "Template channel must match sequence channel."}
            )


class Batch(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"

    name = models.CharField(max_length=255)
    sequence = models.ForeignKey(
        Sequence,
        on_delete=models.CASCADE,
        related_name="batches",
        null=True,
        blank=True,
    )
    reply_to_email = models.EmailField(blank=True)
    # created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class BatchLead(models.Model):
    batch = models.ForeignKey(
        Batch, on_delete=models.CASCADE, related_name="batch_leads"
    )
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="batch_leads")
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    current_step = models.PositiveIntegerField(default=0)
    replied = models.BooleanField(default=False)
    replied_at = models.DateTimeField(null=True, blank=True)
    unsubscribed = models.BooleanField(default=False)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    last_email_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ["batch", "lead"]

    def __str__(self):
        return f"{self.batch.name} - {self.lead}"


class EmailSuppression(models.Model):
    email = models.EmailField(unique=True)
    unsubscribed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class MessageLog(models.Model):
    class Status(models.TextChoices):
        ACCEPTED = "accepted", "Accepted"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        OPENED = "opened", "Opened"
        READ = "read", "Read"
        CLICKED = "clicked", "Clicked"
        FAILED = "failed", "Failed"
        COMPLAINED = "complained", "Complained"
        UNSUBSCRIBED = "unsubscribed", "Unsubscribed"
        REPLIED = "replied", "Replied"

    class LegacyManager(models.Manager):
        def create(self, **kwargs):
            if "to_email" in kwargs:
                kwargs["to_address"] = kwargs.pop("to_email")
                kwargs.setdefault("channel", Channel.EMAIL)
            if "mailgun_message_id" in kwargs:
                kwargs["provider_message_id"] = kwargs.pop("mailgun_message_id")
            return super().create(**kwargs)

    objects = LegacyManager()

    batch_lead = models.ForeignKey(
        BatchLead, on_delete=models.CASCADE, related_name="message_logs"
    )
    template = models.ForeignKey(MessageTemplate, on_delete=models.SET_NULL, null=True)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    step_number = models.PositiveIntegerField()
    to_address = models.CharField(max_length=255)
    subject = models.CharField(max_length=500, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACCEPTED
    )
    provider_message_id = models.CharField(max_length=500, blank=True, db_index=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    error = models.TextField(blank=True)

    def __str__(self):
        return f"{self.to_address} - Step {self.step_number} - {self.status}"


EmailLog = MessageLog


class Opportunity(models.Model):

    STATUS_CHOICES = [
        ('PROSPECTING', 'Prospecting'),
        ('QUALIFICATION', 'Qualification'),
        ('NEEDS_ANALYSIS', 'Needs Analysis'),
        ('VALUE_PROPOSITION', 'Value Proposition'),
        ('IDENTIFY_DECISION_MAKERS', 'Identify Decision Makers'),
        ('PERCEPTION_ANALYSIS', 'Perception Analysis'),
        ('PROPOSAL_PRICE_QUOTE', 'Proposal or Price Quote'),
        ('NEGOTIATION_REVIEW', 'Negotiation or Review'),
        ('CLOSED_WON', 'Closed Won'),
        ('CLOSED_LOST', 'Closed Lost'),
    ]

    lead = models.OneToOneField(
        Lead,
        on_delete=models.CASCADE,
        related_name='opportunity',
        null=True,
        blank=True
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name='opportunities',
        null=True,
        blank=True
    )

  

    enquiry_for = models.CharField(max_length=20, blank=True)

    project_name = models.CharField(max_length=255, blank=True, default="")

    enquiry_date = models.DateField(null=True, blank=True)

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='PROSPECTING'
    )

    source = models.CharField(max_length=30, blank=True)

    assign_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_opportunities'
    )

    expected_close_date = models.DateField(null=True, blank=True)

    estimated_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    probability = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    is_converted_from_lead = models.BooleanField(default=False)

    converted_at = models.DateTimeField(null=True, blank=True)

    converted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='converted_opportunities'
    )

    followup_history = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Opportunities"



class OpportunityModule(models.Model):
    opportunity = models.ForeignKey(
        Opportunity,
        on_delete=models.CASCADE,
        related_name="modules"
    )

    module_number = models.PositiveIntegerField()

    module_name = models.CharField(max_length=255)

    description = models.TextField(blank=True)

    requirements = models.TextField(blank=True)

    estimated_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    estimated_days = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    priority = models.CharField(
        max_length=20,
        choices=[
            ("LOW", "Low"),
            ("MEDIUM", "Medium"),
            ("HIGH", "High"),
        ],
        default="MEDIUM"
    )

    remarks = models.TextField(blank=True)
  
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["module_number"]

    def __str__(self):
        return f"{self.module_number} - {self.module_name}" 
      
      


# quotation
from django.db import models


class Quotation(models.Model):

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("SENT", "Sent"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("REVISION", "Revision"),
        ("CONVERTED", "Converted"),
    ]

    TAX_TYPE_CHOICES = [
        ("INTRA_STATE", "Intra State - CGST + SGST"),
        ("INTER_STATE", "Inter State - IGST"),
        ("INTER_STATE_LUT", "Inter State - IGST 0.1% (LUT Form)"),
        ("SEZ_LUT", "SEZ - 0% (LUT Form)"),
        ("EXPORT", "Export - 0% (Shipping Bill / Air Way Bill)"),
    ]

    # --------------------------------------------------
    # BASIC INFORMATION
    # --------------------------------------------------

    quotation_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True
    )

    quotation_date = models.DateField()

    project_name = models.CharField(max_length=255, blank=True, default="")

    opportunity = models.ForeignKey(
        "Opportunity",
        on_delete=models.PROTECT,
        related_name="quotations",
        null=True,
        blank=True,
    )

    company = models.ForeignKey(
        "Company",
        on_delete=models.PROTECT,
        related_name="quotations",
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT"
    )

    # --------------------------------------------------
    # AMOUNTS
    # --------------------------------------------------

    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    taxable_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    # --------------------------------------------------
    # TAX
    # --------------------------------------------------
    tax_type = models.CharField(
        max_length=30,
        choices=TAX_TYPE_CHOICES,
        blank=True
    )

    tax_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    cgst_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    sgst_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    igst_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    packing_charges = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    # --------------------------------------------------
    # TERMS / DELIVERY
    # --------------------------------------------------

    terms_conditions = models.TextField(
        blank=True
    )

    delivery_timeline = models.CharField(
        max_length=255,
        blank=True
    )

    # --------------------------------------------------
    # QUOTATION DOCUMENT
    # --------------------------------------------------

    quotation_pdf = models.FileField(
        upload_to="quotations/pdfs/",
        null=True,
        blank=True
    )

    pdf_ref_number = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    # --------------------------------------------------
    # FINAL OFFER
    # --------------------------------------------------

    final_offer_generated = models.BooleanField(
        default=False
    )

    cpo_created = models.BooleanField(
        default=False
    )

    cpo_date = models.DateField(
        null=True,
        blank=True,
    )

    cpo_document = models.FileField(
        upload_to="quotations/customer_pos/",
        null=True,
        blank=True,
    )

    fo_date = models.DateField(
        null=True,
        blank=True
    )

    final_offer_pdf = models.FileField(
        upload_to="quotations/final_offers/",
        null=True,
        blank=True
    )

    fo_as_ref = models.BooleanField(
        default=False
    )

    # --------------------------------------------------
    # SEND HISTORY
    # --------------------------------------------------

    send_history = models.JSONField(
        default=list,
        blank=True
    )

    # --------------------------------------------------
    # AUDIT
    # --------------------------------------------------

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_quotations"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.quotation_number


class SalesOrder(models.Model):
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("CONFIRMED", "Confirmed"),
        ("IN_PROGRESS", "In Progress"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
    ]

    so_number = models.CharField(max_length=50, unique=True)
    so_date = models.DateField()
    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.PROTECT,
        related_name="sales_orders",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="sales_orders",
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    taxable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    packing_charges = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_type = models.CharField(max_length=30, blank=True)
    payment_terms = models.TextField(blank=True)
    delivery_terms = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    so_pdf = models.FileField(upload_to="sales_orders/", blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_sales_orders",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.so_number




class QuotationItem(models.Model):

    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.CASCADE,
        related_name="items"
    )

    module = models.ForeignKey(
        "OpportunityModule",
        on_delete=models.PROTECT,
        related_name="quotation_items"
        , null=True,
        blank=True
    )

    module_name = models.CharField(max_length=255, blank=True)

    requirements = models.TextField(blank=True)

    estimated_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    estimated_days = models.PositiveIntegerField(null=True, blank=True)

    priority = models.CharField(
        max_length=20,
        choices=[
            ("LOW", "Low"),
            ("MEDIUM", "Medium"),
            ("HIGH", "High"),
        ],
        default="MEDIUM"
    )

    remarks = models.TextField(blank=True)

    description = models.TextField(
        blank=True
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return (
            f"{self.quotation.quotation_number} - "
            f"{self.module.module_name}"
        )



# Task

class Task(models.Model):
    MODULE_CHOICES = [
        ('LEAD', 'Lead'),
        ('OPPORTUNITY', 'Opportunity'),
        ('QUOTATION', 'Quotation'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]


    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('URGENT', 'Urgent'),
    ]

    REPEAT_FREQUENCY_CHOICES = [
        ('DAILY', 'Daily'),
        ('WEEKLY', 'Weekly'),
        ('MONTHLY', 'Monthly'),
        ('YEARLY', 'Yearly'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # Which module this task belongs to
    module = models.CharField(max_length=20, choices=MODULE_CHOICES)

    # ✅ Simple CharField - no hardcoded choices, controlled by API
    task_regarding = models.CharField(
        max_length=50,
        blank=True,
        help_text="What is this task about? (e.g., Follow Up, Payment, Miscellaneous)"
    )

    # Reference to the specific record in that module
    reference_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g. lead sr_no, PO number, order number (optional for miscellaneous)"
    )

    # Optional company for miscellaneous tasks
    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasks',
        help_text="Optional: For miscellaneous tasks without specific reference"
    )

    followup_date = models.DateField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='MEDIUM')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDING')

    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tasks')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_tasks')

    remarks = models.TextField(blank=True)
    reminder_date = models.DateTimeField(null=True, blank=True)
    is_reminded = models.BooleanField(default=False)

    # Repeat functionality
    is_recurring = models.BooleanField(default=False)
    repeat_frequency = models.CharField(
        max_length=20,
        choices=REPEAT_FREQUENCY_CHOICES,
        blank=True,
        null=True
    )
    repeat_interval = models.PositiveIntegerField(default=1, help_text="Repeat every X days/weeks/months/years")
    repeat_end_date = models.DateField(null=True, blank=True, help_text="When to stop repeating")
    parent_task = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='recurring_instances')

    followup_history = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['followup_date', '-priority']

    def clean(self):
        """Validate that miscellaneous tasks can skip reference_id"""
        from django.core.exceptions import ValidationError

        # If task_regarding is NOT miscellaneous, reference_id is required
        if self.task_regarding and self.task_regarding.upper() != 'MISCELLANEOUS' and not self.reference_id:
            raise ValidationError({
                'reference_id': f'Reference ID is required for {self.task_regarding} tasks in {self.get_module_display()}.'
            })

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.task_regarding and self.task_regarding.upper() == 'MISCELLANEOUS':
            company_name = self.company.name if self.company else 'General'
            return f"{self.title} [{self.module} - Miscellaneous - {company_name}]"
        return f"{self.title} [{self.module} - {self.task_regarding} - {self.reference_id}]"


class TaskAttachment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='task_files/')
    file_name = models.CharField(max_length=255, blank=True)
