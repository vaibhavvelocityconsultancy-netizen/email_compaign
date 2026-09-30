from django.db import transaction
from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import Batch, BatchLead, Channel, MessageLog, MessageTemplate, Sequence, SequenceStep, Lead


class LeadSerializer(serializers.ModelSerializer):
    lead_received_by_name = serializers.SerializerMethodField()
    lead_assign_to_name = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = [
            'sr_no',
            'enquiry_for',
            'enquiry_date',
            'lead_received_by',
            'lead_received_by_name',
            'lead_assign_to',
            'lead_assign_to_name',
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
        read_only_fields = ['sr_no', 'lead_received_by_name', 'lead_assign_to_name', 'tracker', 'followup_history', 'is_active', 'created_at', 'updated_at']

    lead_received_by = serializers.PrimaryKeyRelatedField(queryset=get_user_model().objects.filter(is_active=True))
    lead_assign_to = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )

    def get_lead_received_by_name(self, lead):
        return lead.lead_received_by.get_full_name() or lead.lead_received_by.get_username()

    def get_lead_assign_to_name(self, lead):
        if not lead.lead_assign_to:
            return None
        return lead.lead_assign_to.get_full_name() or lead.lead_assign_to.get_username()
        
        
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
            BatchLead(batch=batch, lead=lead)
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
                BatchLead(batch=batch, lead=lead)
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