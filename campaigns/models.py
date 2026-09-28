from django.db import models

# Create your models here.

class Lead(models.Model):
    ENQUIRY_FOR=[
        
    ]
    SOURCE_CHOICES = [
        ('WEBSITE',         'Website'),
        ('SOCIAL_MEDIA',    'Social Media'),
        ('GOOGLE',          'Google Search'),
        ('ADVERTISEMENT',   'Advertisement'),
        ('REFERENCE',       'Reference'),
        ('EXISTING_CLIENT', 'Existing Client'),
        ('COLD_CALL',       'Cold Call'),
        ('EMAIL_MARKETING', 'Email Marketing'),
        ('OTHER',           'Other'),
    ]

    STATUS_CHOICES = [
        ('NEW',    'New'),
        ('ACTIVE', 'Active'),
        ('JUNK',   'Junk'),
        ('HOT',    'Hot'),
        ('COLD',   'Cold'),
    ]

    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    company = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    source = models.CharField(
    max_length=30,
    choices=SOURCE_CHOICES,
    default='OTHER'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='NEW'
    )
    
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    
    

class EmailTemplate(models.Model):
    name = models.CharField(max_length=255)
    subject = models.CharField(max_length=500)
    body = models.TextField()
    signature = models.TextField(blank=True)
    logo = models.ImageField(upload_to='email_logos/', null=True, blank=True)
    attachment = models.FileField(upload_to='email_attachments/', null=True, blank=True)
    # created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        
        return self.name


class EmailSequence(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class EmailSequenceStep(models.Model):
    sequence = models.ForeignKey(EmailSequence, on_delete=models.CASCADE, related_name='steps')
    step_number = models.PositiveIntegerField()
    template = models.ForeignKey(EmailTemplate, on_delete=models.CASCADE)
    delay_days = models.PositiveIntegerField(default=0)
    delay_minutes = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['step_number']
        unique_together = ['sequence', 'step_number']

    def __str__(self):
        return f"{self.sequence.name} - Step {self.step_number}"


class Batch(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        PAUSED = 'paused', 'Paused'
        COMPLETED = 'completed', 'Completed'

    name = models.CharField(max_length=255)
    sequence = models.ForeignKey(EmailSequence, on_delete=models.CASCADE, related_name='batches')
    # created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class BatchLead(models.Model):
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='batch_leads')
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='batch_leads')
    email = models.EmailField()
    current_step = models.PositiveIntegerField(default=0)
    replied = models.BooleanField(default=False)
    replied_at = models.DateTimeField(null=True, blank=True)
    unsubscribed = models.BooleanField(default=False)
    completed = models.BooleanField(default=False)
    last_email_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['batch', 'lead']

    def __str__(self):
        return f"{self.batch.name} - {self.lead.company_name}"


class EmailLog(models.Model):
    class Status(models.TextChoices):
        SENT = 'sent', 'Sent'
        FAILED = 'failed', 'Failed'
        REPLIED = 'replied', 'Replied'

    batch_lead = models.ForeignKey(BatchLead, on_delete=models.CASCADE, related_name='email_logs')
    template = models.ForeignKey(EmailTemplate, on_delete=models.SET_NULL, null=True)
    step_number = models.PositiveIntegerField()
    to_email = models.EmailField()
    subject = models.CharField(max_length=500)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SENT)
    mailgun_message_id = models.CharField(max_length=500, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    error = models.TextField(blank=True)

    def __str__(self):
        return f"{self.to_email} - Step {self.step_number} - {self.status}"
        
    