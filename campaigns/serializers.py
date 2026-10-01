from django.db import transaction
from rest_framework import serializers
from .models import Batch, BatchLead, Channel, Company, CompanyContact, MessageLog, MessageTemplate, Sequence, SequenceStep, Lead


class LeadSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(write_only=True, max_length=200)
    company_address = serializers.CharField(write_only=True, required=False, allow_blank=True)
    company_city = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=100)
    company_state = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=100)
    company_pincode = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=10)
    company_country = serializers.CharField(write_only=True, required=False, max_length=100)
    company_gst_number = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=50)
    contact_name = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=100)
    contact_designation = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=100)
    contact_mobile = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=20)
    contact_email = serializers.EmailField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Lead
        fields = [
            'sr_no',
            'company',
            'contact',
            'company_name',
            'company_address',
            'company_city',
            'company_state',
            'company_pincode',
            'company_country',
            'company_gst_number',
            'contact_name',
            'contact_designation',
            'contact_mobile',
            'contact_email',
            'enquiry_for',
            'enquiry_date',
            'source',
            'status',
            'followup_date',
            'followup_remarks',
            'is_opportunity',
            'tracker',
            'followup_history',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['sr_no', 'company', 'contact', 'tracker', 'followup_history', 'is_active', 'created_at', 'updated_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        company = instance.company
        contact = instance.contact
        data.update({
            'company_name': company.name if company else '',
            'company_address': company.address if company else '',
            'company_city': company.city if company else '',
            'company_state': company.state if company else '',
            'company_pincode': company.pincode if company else '',
            'company_country': company.country if company else 'India',
            'company_gst_number': company.gst_number if company else '',
            'contact_name': contact.name if contact else '',
            'contact_designation': contact.designation if contact else '',
            'contact_mobile': contact.phone if contact else '',
            'contact_email': contact.email if contact else '',
        })
        return data

    @staticmethod
    def _save_company(validated_data, instance=None):
        company_data = {
            'name': validated_data.pop('company_name'),
            'address': validated_data.pop('company_address', ''),
            'city': validated_data.pop('company_city', ''),
            'state': validated_data.pop('company_state', ''),
            'pincode': validated_data.pop('company_pincode', ''),
            'country': validated_data.pop('company_country', 'India'),
            'gst_number': validated_data.pop('company_gst_number', ''),
        }
        company = instance.company if instance and instance.company and instance.company.name.casefold() == company_data['name'].casefold() else None
        if company is None:
            company = Company.objects.filter(name__iexact=company_data['name']).first()
        if company is None:
            return Company.objects.create(**company_data)
        for field, value in company_data.items():
            setattr(company, field, value)
        company.save()
        return company

    @staticmethod
    def _save_contact(validated_data, company, instance=None):
        contact_name = validated_data.pop('contact_name', '').strip()
        designation = validated_data.pop('contact_designation', '')
        phone = validated_data.pop('contact_mobile', '')
        email = validated_data.pop('contact_email', '')
        if not contact_name:
            return None

        contact = instance.contact if instance and instance.contact and instance.contact.company_id == company.pk and instance.contact.name.casefold() == contact_name.casefold() else None
        if contact is None:
            contact = company.contacts.filter(name__iexact=contact_name).first()
        if contact is None:
            contact = CompanyContact(company=company, name=contact_name)
        contact.designation = designation
        contact.phone = phone
        contact.email = email
        if not contact.pk and not company.contacts.filter(is_primary=True, is_active=True).exists():
            contact.is_primary = True
        contact.save()
        return contact

    @transaction.atomic
    def create(self, validated_data):
        company = self._save_company(validated_data)
        contact = self._save_contact(validated_data, company)
        return Lead.objects.create(company=company, contact=contact, **validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        company = self._save_company(validated_data, instance)
        contact = self._save_contact(validated_data, company, instance)
        instance.company = company
        instance.contact = contact
        return super().update(instance, validated_data)
        
        
class MessageTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageTemplate
        fields = [
            'id',
            'channel',
            'name',
            'subject',
            'body',
            'signature',
            'logo',
            'attachment',
            'wa_template_name',
            'wa_language',
            'wa_status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        
        
class SequenceStepSerializer(serializers.ModelSerializer):
    sequence = serializers.PrimaryKeyRelatedField(
        queryset=Sequence.objects.all(),
        required=False,
    )

    class Meta:
        model = SequenceStep
        fields = [
            'id',
            'sequence',
            'step_number',
            'template',
            'delay_days',
            'delay_minutes',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        sequence = attrs.get('sequence', getattr(self.instance, 'sequence', None))
        template = attrs.get('template', getattr(self.instance, 'template', None))
        if sequence and template and sequence.channel != template.channel:
            raise serializers.ValidationError({'template': 'Template channel must match sequence channel.'})
        return attrs


class NestedSequenceStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = SequenceStep
        fields = [
            'id',
            'step_number',
            'template',
            'delay_days',
            'delay_minutes',
        ]
        read_only_fields = ['id']
        validators = []


class SequenceSerializer(serializers.ModelSerializer):
    steps = NestedSequenceStepSerializer(many=True, required=False)

    class Meta:
        model = Sequence
        fields = [
            'id',
            'channel',
            'name',
            'description',
            'created_at',
            'steps',
        ]
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        channel = attrs.get('channel', getattr(self.instance, 'channel', Channel.EMAIL))
        steps = attrs.get('steps')
        if steps is None and self.instance:
            templates = [step.template for step in self.instance.steps.select_related('template')]
        else:
            templates = [step['template'] for step in (steps or [])]
        for template in templates:
            if template.channel != channel:
                raise serializers.ValidationError({'steps': 'Every template channel must match the sequence channel.'})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        steps_data = validated_data.pop('steps', [])
        sequence = super().create(validated_data)
        for step_data in steps_data:
            step_data.pop('sequence', None)
            SequenceStep.objects.create(sequence=sequence, **step_data)
        return sequence

    @transaction.atomic
    def update(self, instance, validated_data):
        steps_data = validated_data.pop('steps', None)
        sequence = super().update(instance, validated_data)
        if steps_data is not None:
            sequence.steps.all().delete()
            for step_data in steps_data:
                step_data.pop('sequence', None)
                SequenceStep.objects.create(sequence=sequence, **step_data)
        return sequence
        

class BatchSerializer(serializers.ModelSerializer):
    lead_ids = serializers.PrimaryKeyRelatedField(
        queryset=Lead.objects.all(),
        many=True,
        required=False,
        write_only=True,
    )

    class Meta:
        model = Batch
        fields = [
            'id',
            'name',
            'sequence',
            'lead_ids',
            'enquiry_date_from',
            'enquiry_date_to',
            'status',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    @transaction.atomic
    def create(self, validated_data):
        leads = validated_data.pop('lead_ids', [])
        batch = super().create(validated_data)
        BatchLead.objects.bulk_create([
            BatchLead(
                batch=batch,
                lead=lead,
                email=lead.contact.email if lead.contact else '',
                phone=lead.contact.phone if lead.contact else '',
            )
            for lead in leads
        ])
        return batch

    @transaction.atomic
    def update(self, instance, validated_data):
        leads = validated_data.pop('lead_ids', None)
        batch = super().update(instance, validated_data)
        if leads is not None:
            existing_ids = set(batch.batch_leads.values_list('lead_id', flat=True))
            BatchLead.objects.bulk_create([
                BatchLead(
                    batch=batch,
                    lead=lead,
                    email=lead.contact.email if lead.contact else '',
                    phone=lead.contact.phone if lead.contact else '',
                )
                for lead in leads
                if lead.pk not in existing_ids
            ])
        return batch


class BatchLeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchLead
        fields = [
            'id',
            'batch',
            'lead',
            'email',
            'phone',
            'current_step',
            'replied',
            'replied_at',
            'unsubscribed',
            'completed',
            'last_email_sent_at',
        ]
        read_only_fields = ['id']


class MessageLogSerializer(serializers.ModelSerializer):
    batch = serializers.IntegerField(source='batch_lead.batch_id', read_only=True)
    lead = serializers.IntegerField(source='batch_lead.lead_id', read_only=True)
    template_name = serializers.CharField(source='template.name', read_only=True, allow_null=True)

    class Meta:
        model = MessageLog
        fields = [
            'id',
            'batch',
            'lead',
            'step_number',
            'channel',
            'to_address',
            'status',
            'sent_at',
            'subject',
            'template_name',
            'error',
        ]