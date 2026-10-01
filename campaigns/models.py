from django.core.exceptions import ValidationError
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
    ]

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
    enquiry_for = models.CharField(max_length=20, choices=ENQUIRY_FOR_CHOICES)

    # Enquirey details
    enquiry_date = models.DateField()
    # lead_received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='received_enquiries')
    # lead_assign_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_leads')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
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

    def __str__(self):
        return f"Enquiry #{self.sr_no}"


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
        Sequence, on_delete=models.CASCADE, related_name="batches"
    )
    enquiry_date_from = models.DateField(null=True, blank=True)
    enquiry_date_to = models.DateField(null=True, blank=True)
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
    completed = models.BooleanField(default=False)
    last_email_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ["batch", "lead"]

    def __str__(self):
        return f"{self.batch.name} - {self.lead}"


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
    """Opportunity created from Lead - this is where items are added"""
    
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
    enquiry_for = models.CharField(max_length=20, choices=Lead.ENQUIRY_FOR_CHOICES, blank=True)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='opportunities', null=True, blank=True)
    enquiry_date = models.DateField(null=True, blank=True) 
    # Link to original lead
    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name='opportunity', null=True, blank=True)
    
    # Opportunity specific fields
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='PROSPECTING')
    source = models.CharField(max_length=20, blank=True)
    assign_to = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_opportunities')
    expected_close_date = models.DateField(null=True, blank=True)
    
    # Conversion info
    is_converted_from_lead = models.BooleanField(default=False)
    converted_at = models.DateTimeField(auto_now_add=True)
    converted_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='converted_opportunities')
    
    # Follow-up tracking
    followup_history = models.JSONField(default=list, blank=True)
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Opportunities"
        
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and self.lead:
            self.lead.company.is_contact = False
            self.lead.company.save(update_fields=['is_contact'])
