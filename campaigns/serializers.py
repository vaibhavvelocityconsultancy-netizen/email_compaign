from rest_framework import serializers
from .models import Batch, BatchLead, EmailSequence, EmailSequenceStep, EmailTemplate, Lead


class LeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = "__all__"
        
        
class EmailTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = [
            'id',
            'name',
            'subject',
            'body',
            'signature',
            'logo',
            'attachment',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        
        
class EmailSequenceSerializer(serializers.ModelSerializer): 
    class Meta:
        model = EmailSequence
        fields = [
            'id',
            'name',
            'description',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']
        
        
class EmailSequenceStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailSequenceStep
        fields = [
            'id',
            'sequence',
            'step_number',
            'template',
            'delay_days',
            'delay_minutes',
        ]
        read_only_fields = ['id']
        

class BatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Batch
        fields = [
            'id',
            'name',
            'sequence',
            'status',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class BatchLeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchLead
        fields = [
            'id',
            'batch',
            'lead',
            'email',
            'current_step',
            'replied',
            'replied_at',
            'unsubscribed',
            'completed',
            'last_email_sent_at',
        ]
        read_only_fields = ['id']