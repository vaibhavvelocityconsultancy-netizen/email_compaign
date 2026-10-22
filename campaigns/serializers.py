from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from .models import (
    Batch,
    BatchLead,
    Channel,
    City,
    Company,
    CompanyContact,
    Country,
    EmailSuppression,
    MessageLog,
    MessageTemplate,
    Opportunity,
    OpportunityModule,
    Quotation,
    QuotationItem,
    SalesOrder,
    Sequence,
    SequenceStep,
    State,
    Lead,
    Task,
    TaskAttachment,
)

# -------------------Masters - Country, State, City, Company, CompanyContact Serializer -------------------
class CountrySerializer(serializers.ModelSerializer):
    code = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=10
    )

    class Meta:
        model = Country
        fields = ["id", "name", "code", "is_active"]

    def validate_code(self, value):
        return value or None


class StateSerializer(serializers.ModelSerializer):
    class Meta:
        model = State
        fields = ["id", "name", "country", "is_active"]


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ["id", "name", "state", "is_active"]


class CompanySerializer(serializers.ModelSerializer):
    contacts_count = serializers.IntegerField(read_only=True)

    city_name = serializers.CharField(source="city.name", read_only=True)
    state_name = serializers.CharField(source="state.name", read_only=True)
    country_name = serializers.CharField(source="country.name", read_only=True)

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "is_contact",
            "address",
            "city",
            "city_name",
            "state",
            "state_name",
            "pincode",
            "country",
            "country_name",
            "gst_number",
            "is_active",
            "contacts_count",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "is_contact",
            "is_active",
            "contacts_count",
            "created_at",
            "city_name",
            "state_name",
            "country_name",
        ]


class CompanyContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyContact
        fields = [
            "id",
            "company",
            "name",
            "designation",
            "phone",
            "email",
            "is_primary",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "company", "is_active", "created_at"]


# ---------------- masters serializer ends -------------------

# ------------------- Lead Serializer -------------------
class LeadSerializer(serializers.ModelSerializer):
    unsubscribed = serializers.SerializerMethodField()
    company_name = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=200
    )
    company_address = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    company_city = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=100
    )
    company_state = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=100
    )
    company_pincode = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=10
    )
    company_country = serializers.CharField(
        write_only=True, required=False, max_length=100
    )
    company_gst_number = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=50
    )
    contact_name = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=100
    )
    contact_designation = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=100
    )
    contact_mobile = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=20
    )
    contact_email = serializers.EmailField(
        write_only=True, required=False, allow_blank=True
    )

    class Meta:
        model = Lead
        fields = [
            "sr_no",
            "unsubscribed",
            "company",
            "contact",
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
            "tracker",
            "followup_history",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "sr_no",
            "unsubscribed",
            "company",
            "contact",
            "tracker",
            "followup_history",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        company = instance.company
        contact = instance.contact
        data.update(
            {
                "company_name": company.name if company else "",
                "company_address": company.address if company else "",
                "company_city": company.city.name if company and company.city else "",
                "company_state": company.state.name if company and company.state else "",
                "company_pincode": company.pincode if company else "",
                "company_country": company.country.name if company and company.country else "India",
                "company_gst_number": company.gst_number if company else "",
                "contact_name": contact.name if contact else "",
                "contact_designation": contact.designation if contact else "",
                "contact_mobile": contact.phone if contact else "",
                "contact_email": contact.email if contact else "",
            }
        )
        return data

    def get_unsubscribed(self, instance):
        email = (
            (instance.contact.email if instance.contact else "")
            or instance.email
            or ""
        ).strip().lower()
        if not email:
            return False

        suppressed_emails = self.context.get("suppressed_emails")
        if suppressed_emails is not None:
            return email in suppressed_emails
        return EmailSuppression.objects.filter(email__iexact=email).exists()

    @staticmethod
    def _resolve_master(model_class, value, **filters):
        if value in (None, ""):
            return None
        if isinstance(value, model_class):
            return value
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            queryset = model_class.objects.filter(**filters)
            if value.isdigit():
                obj = queryset.filter(pk=int(value)).first()
                if obj is not None:
                    return obj
            obj = queryset.filter(name__iexact=value).first()
            if obj is not None:
                return obj
            if model_class is Country:
                return model_class.objects.create(name=value)
            if model_class is State:
                country = filters.get("country")
                if country is None:
                    return None
                return model_class.objects.create(country=country, name=value)
            if model_class is City:
                state = filters.get("state")
                if state is None:
                    return None
                return model_class.objects.create(state=state, name=value)
            return None
        if isinstance(value, int):
            return model_class.objects.filter(pk=value, **filters).first()
        return None

    @classmethod
    def _save_company(cls, validated_data, instance=None):
        company_name = validated_data.pop("company_name", "").strip()
        company_address = validated_data.pop("company_address", "")
        company_pincode = validated_data.pop("company_pincode", "")
        company_gst_number = validated_data.pop("company_gst_number", "")
        company_country = validated_data.pop("company_country", "India")
        company_state = validated_data.pop("company_state", "")
        company_city = validated_data.pop("company_city", "")
        if not company_name:
            return None

        company_data = {
            "name": company_name,
            "address": company_address,
            "pincode": company_pincode,
            "gst_number": company_gst_number,
        }

        country = cls._resolve_master(
            Country,
            company_country,
        )
        state = cls._resolve_master(
            State,
            company_state,
            country=country,
        )
        city = cls._resolve_master(
            City,
            company_city,
            state=state,
        )

        if country is None:
            country = Country.objects.filter(name__iexact="India").first() or Country.objects.create(name="India")
        if state is not None:
            company_data["state"] = state
        if city is not None:
            company_data["city"] = city
        company_data["country"] = country

        company = (
            instance.company
            if instance
            and instance.company
            and instance.company.name.casefold() == company_name.casefold()
            else None
        )
        if company is None:
            company = Company.objects.filter(name__iexact=company_name).first()
        if company is None:
            return Company.objects.create(**company_data)
        for field, value in company_data.items():
            setattr(company, field, value)
        company.save()
        return company

    @staticmethod
    def _save_contact(validated_data, company, instance=None):
        contact_name = validated_data.pop("contact_name", "").strip()
        designation = validated_data.pop("contact_designation", "")
        phone = validated_data.pop("contact_mobile", "")
        email = validated_data.pop("contact_email", "")
        if not company or not contact_name:
            return None

        contact = (
            instance.contact
            if instance
            and instance.contact
            and instance.contact.company_id == company.pk
            and instance.contact.name.casefold() == contact_name.casefold()
            else None
        )
        if contact is None:
            contact = company.contacts.filter(name__iexact=contact_name).first()
        if contact is None:
            contact = CompanyContact(company=company, name=contact_name)
        contact.designation = designation
        contact.phone = phone
        contact.email = email
        if (
            not contact.pk
            and not company.contacts.filter(is_primary=True, is_active=True).exists()
        ):
            contact.is_primary = True
        contact.save()
        return contact

    @transaction.atomic
    def create(self, validated_data):
        company = self._save_company(validated_data)
        contact = self._save_contact(validated_data, company)
        lead = Lead.objects.create(company=company, contact=contact, **validated_data)
        self._sync_opportunity(lead)
        return lead

    @transaction.atomic
    def update(self, instance, validated_data):
        company = self._save_company(validated_data, instance)
        contact = self._save_contact(validated_data, company, instance)
        instance.company = company
        instance.contact = contact
        lead = super().update(instance, validated_data)
        self._sync_opportunity(lead)
        return lead

    @staticmethod
    def _sync_opportunity(lead):
        if not lead.is_opportunity:
            if hasattr(lead, "opportunity"):
                lead.opportunity.is_active = False
                lead.opportunity.save(update_fields=["is_active", "updated_at"])
            return

        opportunity, created = Opportunity.objects.get_or_create(
            lead=lead,
            defaults={
                "company": lead.company,
                "source": lead.source,
                "expected_close_date": lead.followup_date,
                "is_converted_from_lead": True,
                "converted_at": timezone.now(),
            },
        )
        if not created:
            opportunity.company = lead.company
            opportunity.source = lead.source
            opportunity.expected_close_date = lead.followup_date
            opportunity.is_active = True
            opportunity.save(update_fields=["company", "source", "expected_close_date", "is_active", "updated_at"])
      
# ------------ lead serializer ends -----------------------------
      
      

# -------- message template serializer ----------------------------
class MessageTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageTemplate
        fields = [
            "id",
            "channel",
            "name",
            "subject",
            "body",
            "signature",
            "logo",
            "attachment",
            "wa_template_name",
            "wa_language",
            "wa_status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class SequenceStepSerializer(serializers.ModelSerializer):
    sequence = serializers.PrimaryKeyRelatedField(
        queryset=Sequence.objects.all(),
        required=False,
    )

    class Meta:
        model = SequenceStep
        fields = [
            "id",
            "sequence",
            "step_number",
            "template",
            "delay_days",
            "delay_minutes",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        sequence = attrs.get("sequence", getattr(self.instance, "sequence", None))
        template = attrs.get("template", getattr(self.instance, "template", None))
        if sequence and template and sequence.channel != template.channel:
            raise serializers.ValidationError(
                {"template": "Template channel must match sequence channel."}
            )
        return attrs


class NestedSequenceStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = SequenceStep
        fields = [
            "id",
            "step_number",
            "template",
            "delay_days",
            "delay_minutes",
        ]
        read_only_fields = ["id"]
        validators = []


class SequenceSerializer(serializers.ModelSerializer):
    steps = NestedSequenceStepSerializer(many=True, required=False)

    class Meta:
        model = Sequence
        fields = [
            "id",
            "channel",
            "name",
            "description",
            "created_at",
            "steps",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        channel = attrs.get("channel", getattr(self.instance, "channel", Channel.EMAIL))
        steps = attrs.get("steps")
        if steps is None and self.instance:
            templates = [
                step.template for step in self.instance.steps.select_related("template")
            ]
        else:
            templates = [step["template"] for step in (steps or [])]
        for template in templates:
            if template.channel != channel:
                raise serializers.ValidationError(
                    {"steps": "Every template channel must match the sequence channel."}
                )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        steps_data = validated_data.pop("steps", [])
        sequence = super().create(validated_data)
        for step_data in steps_data:
            step_data.pop("sequence", None)
            SequenceStep.objects.create(sequence=sequence, **step_data)
        return sequence

    @transaction.atomic
    def update(self, instance, validated_data):
        steps_data = validated_data.pop("steps", None)
        sequence = super().update(instance, validated_data)
        if steps_data is not None:
            sequence.steps.all().delete()
            for step_data in steps_data:
                step_data.pop("sequence", None)
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
            "id",
            "name",
            "sequence",
            "reply_to_email",
            "lead_ids",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    @staticmethod
    def _make_batch_leads(batch, leads, existing_ids=None):
        existing_ids = existing_ids or set()
        eligible_leads = [lead for lead in leads if lead.pk not in existing_ids]
        emails = [
            ((lead.contact.email if lead.contact else "") or lead.email or "")
            .strip()
            .lower()
            for lead in eligible_leads
            if (lead.contact and lead.contact.email) or lead.email
        ]
        suppressed_emails = set(
            EmailSuppression.objects.filter(email__in=emails).values_list(
                "email", flat=True
            )
        )
        now = timezone.now()
        batch_leads = []
        for lead in eligible_leads:
            email = ((lead.contact.email if lead.contact else "") or lead.email or "")
            phone = ((lead.contact.phone if lead.contact else "") or lead.phone or "")
            is_suppressed = email.strip().lower() in suppressed_emails
            batch_leads.append(
                BatchLead(
                    batch=batch,
                    lead=lead,
                    email=email,
                    phone=phone,
                    unsubscribed=is_suppressed,
                    unsubscribed_at=now if is_suppressed else None,
                )
            )
        return batch_leads

    @transaction.atomic
    def create(self, validated_data):
        leads = validated_data.pop("lead_ids", [])
        batch = super().create(validated_data)
        BatchLead.objects.bulk_create(self._make_batch_leads(batch, leads))
        return batch

    @transaction.atomic
    def update(self, instance, validated_data):
        leads = validated_data.pop("lead_ids", None)
        batch = super().update(instance, validated_data)
        if leads is not None:
            existing_ids = set(batch.batch_leads.values_list("lead_id", flat=True))
            BatchLead.objects.bulk_create(
                self._make_batch_leads(batch, leads, existing_ids)
            )
        return batch


class BatchLeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchLead
        fields = [
            "id",
            "batch",
            "lead",
            "email",
            "phone",
            "current_step",
            "replied",
            "replied_at",
            "unsubscribed",
            "unsubscribed_at",
            "completed",
            "last_email_sent_at",
        ]
        read_only_fields = ["id", "unsubscribed", "unsubscribed_at"]


class MessageLogSerializer(serializers.ModelSerializer):
    batch = serializers.IntegerField(source="batch_lead.batch_id", read_only=True)
    lead = serializers.IntegerField(source="batch_lead.lead_id", read_only=True)
    template_name = serializers.CharField(
        source="template.name", read_only=True, allow_null=True
    )

    class Meta:
        model = MessageLog
        fields = [
            "id",
            "batch",
            "lead",
            "step_number",
            "channel",
            "to_address",
            "status",
            "sent_at",
            "subject",
            "template_name",
            "error",
        ]

# ----------- email & whatsapp compaign ends -----

# Opportunity Module Serializer
class OpportunityModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpportunityModule
        fields = [
            'id',
            'opportunity',
            'module_number',
            'module_name',
            'description',
            'requirements',
            'estimated_cost',
            'estimated_days',
            'priority',
            'remarks',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'opportunity', 'created_at', 'updated_at']
        extra_kwargs = {'module_number': {'required': False}}

    def validate_module_number(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError('Module number must be positive.')
        return value

    def validate_module_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Module name cannot be empty.')
        return value

    def validate_estimated_cost(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('Estimated cost cannot be negative.')
        return value

    def validate_estimated_days(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('Estimated days cannot be negative.')
        return value


OpportunityModuleCreateSerializer = OpportunityModuleSerializer


class OpportunityCreateSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(write_only=True, required=False)
    project_name = serializers.CharField(required=False, allow_blank=True)
    enquiry_for = serializers.CharField(write_only=True, required=False)
    enquiry_date = serializers.DateField(
        write_only=True,
        required=False,
        allow_null=True,
        input_formats=["%m-%d-%Y", "%Y-%m-%d"],
    )
    modules = OpportunityModuleSerializer(
        many=True,
        required=False
    )

    class Meta:
        model = Opportunity
        fields = [
            'id',
            'lead',
            'company',
            'company_name',
            'project_name',
            'enquiry_for',
            'enquiry_date',
            'status',
            'source',
            'expected_close_date',
            'estimated_value',
            'probability',
            'is_converted_from_lead',
            'converted_at',
            'followup_history',
            'created_at',
            'updated_at',
            'is_active',
            'modules',
        ]
        extra_kwargs = {
            'id': {'read_only': True},
            'lead': {
                'required': False,
                'allow_null': True
            },
            'is_converted_from_lead': {'read_only': True},
            'converted_at': {'read_only': True},
            'followup_history': {'read_only': True},
            'created_at': {'read_only': True},
            'updated_at': {'read_only': True},
            'is_active': {'read_only': True},
        }

    def validate_lead(self, lead):
        if lead and hasattr(lead, 'opportunity'):
            raise serializers.ValidationError(
                f'Lead #{lead.sr_no} already has an opportunity.'
            )
        return lead

    def create(self, validated_data):
        modules_data = validated_data.pop('modules', [])
        company_name = validated_data.pop('company_name', '').strip()
        project_name = validated_data.pop('project_name', '').strip()
        enquiry_for = validated_data.pop('enquiry_for', None)
        enquiry_date = validated_data.pop('enquiry_date', None)

        lead = validated_data.get('lead')
        company = validated_data.get('company') or (lead.company if lead else None)
        if company is None and company_name:
            company = Company.objects.filter(name__iexact=company_name).first()
            if company is None:
                company = Company.objects.create(name=company_name)
        if company is not None:
            validated_data['company'] = company
            company_name = company.name
        if lead is not None:
            enquiry_for = enquiry_for or lead.enquiry_for
            enquiry_date = enquiry_date or lead.enquiry_date
        if project_name:
            validated_data['project_name'] = project_name
        if enquiry_for:
            validated_data['enquiry_for'] = enquiry_for
        if enquiry_date:
            validated_data['enquiry_date'] = enquiry_date
        opportunity = Opportunity.objects.create(
            **validated_data,
            is_converted_from_lead=bool(lead)
        )

        for index, module_data in enumerate(modules_data, start=1):
            module_data.setdefault('module_number', index)

            OpportunityModule.objects.create(
                opportunity=opportunity,
                **module_data
            )

        return opportunity

    def update(self, instance, validated_data):
        modules_data = validated_data.pop('modules', None)
        company_name = validated_data.pop('company_name', '').strip()
        project_name = validated_data.pop('project_name', None)
        enquiry_for = validated_data.pop('enquiry_for', None)
        enquiry_date = validated_data.pop('enquiry_date', None)
        if project_name is not None:
            validated_data['project_name'] = project_name.strip()
        if enquiry_for:
            validated_data['enquiry_for'] = enquiry_for
        if enquiry_date:
            validated_data['enquiry_date'] = enquiry_date
        if company_name and 'company' not in validated_data:
            company = Company.objects.filter(name__iexact=company_name).first()
            if company is None:
                company = Company.objects.create(name=company_name)
            validated_data['company'] = company
        opportunity = super().update(instance, validated_data)

        if modules_data is not None:
            opportunity.modules.all().delete()
            for index, module_data in enumerate(modules_data, start=1):
                module_data.setdefault('module_number', index)
                OpportunityModule.objects.create(
                    opportunity=opportunity,
                    **module_data
                )

        return opportunity

    def to_representation(self, instance):
        data = super().to_representation(instance)
        lead = instance.lead
        data.update({
            'company_name': instance.company.name if instance.company else '',
            'project_name': instance.project_name,
            'enquiry_for': instance.enquiry_for or (lead.enquiry_for if lead else ''),
            'enquiry_date': instance.enquiry_date or (lead.enquiry_date if lead else None),
        })
        return data


class QuotationItemSerializer(serializers.ModelSerializer):
    module_name = serializers.CharField(read_only=True)

    class Meta:
        model = QuotationItem
        fields = [
            "id",
            "quotation",
            "module",
            "module_name",
            "description",
            "requirements",
            "estimated_cost",
            "estimated_days",
            "priority",
            "remarks",
            "amount",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "quotation", "created_at", "updated_at"]

    def validate_module_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Module name cannot be empty.")
        return value

    def validate_amount(self, value):
        if value < 0:
            raise serializers.ValidationError("Amount cannot be negative.")
        return value

    def validate_estimated_cost(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Estimated cost cannot be negative.")
        return value

    def validate_estimated_days(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Estimated days cannot be negative.")
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not instance.module_name and instance.module:
            data["module_name"] = instance.module.module_name
        return data


class FinalOfferItemUpdateSerializer(serializers.Serializer):
    module = serializers.PrimaryKeyRelatedField(
        queryset=OpportunityModule.objects.all(),
        required=False,
        allow_null=True,
    )
    module_name = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    requirements = serializers.CharField(required=False, allow_blank=True)
    estimated_cost = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True, min_value=0
    )
    estimated_days = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    priority = serializers.ChoiceField(
        choices=["LOW", "MEDIUM", "HIGH"], required=False
    )
    remarks = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)


class FinalOfferUpdateSerializer(serializers.Serializer):
    fo_date = serializers.DateField(
        input_formats=["%Y-%m-%d", "%m-%d-%Y"],
    )
    items = FinalOfferItemUpdateSerializer(many=True)


class QuotationSerializer(serializers.ModelSerializer):
    items = QuotationItemSerializer(many=True, required=False)
    company_name = serializers.SerializerMethodField()
    company_address = serializers.SerializerMethodField()
    company_pincode = serializers.SerializerMethodField()
    company_contacts = serializers.SerializerMethodField()
    company_id = serializers.SerializerMethodField()
    selected_company_id = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.filter(is_active=True),
        write_only=True,
        required=False,
    )
    company_city = serializers.SerializerMethodField()
    company_state = serializers.SerializerMethodField()
    project_name = serializers.CharField(required=False, allow_blank=True)
    created_by = serializers.IntegerField(source="created_by_id", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    tax_type_display = serializers.CharField(source="get_tax_type_display", read_only=True)
    quotation_date = serializers.DateField(
        format="%m-%d-%Y",
        input_formats=["%m-%d-%Y", "%Y-%m-%d"],
    )
    fo_date = serializers.DateField(format="%Y-%m-%d", required=False, allow_null=True, read_only=True)
    cpo_date = serializers.DateField(
        format="%Y-%m-%d",
        input_formats=["%Y-%m-%d", "%m-%d-%Y"],
        required=False,
        allow_null=True,
    )
    cpo_document = serializers.FileField(required=False, allow_null=True)

    class Meta:
        model = Quotation
        fields = [
            "id",
            "quotation_number",
            "quotation_date",
            "opportunity",
            "company_name",
            "company_address",
            "company_pincode",
            "company_contacts",
            "company_id",
            "selected_company_id",
            "company_city",
            "company_state",
            "project_name",
            "status",
            "status_display",
            "subtotal",
            "discount",
            "taxable_amount",
            "tax_type",
            "tax_type_display",
            "tax_percentage",
            "tax_amount",
            "cgst_amount",
            "sgst_amount",
            "igst_amount",
            "packing_charges",
            "total_amount",
            "terms_conditions",
            "delivery_timeline",
            "quotation_pdf",
            "pdf_ref_number",
            "final_offer_generated",
            "cpo_created",
            "cpo_date",
            "cpo_document",
            "fo_date",
            "final_offer_pdf",
            "fo_as_ref",
            "send_history",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
            "items",
        ]
        read_only_fields = [
            "id",
            "company_id",
            "status_display",
            "tax_type_display",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]

    def get_created_by_name(self, obj):
        user = obj.created_by
        return user.get_full_name() or user.get_username() if user else None

    def get_company_name(self, obj):
        if obj.company_id:
            return obj.company.name
        opportunity = obj.opportunity
        if opportunity is None:
            return ""
        company = opportunity.company
        if company:
            return company.name
        try:
            lead = opportunity.lead
        except Lead.DoesNotExist:
            lead = None
        return lead.company.name if lead and lead.company else ""

    def get_company_address(self, obj):
        company = self._get_related_company(obj)
        return company.address if company else ""

    def get_company_pincode(self, obj):
        company = self._get_related_company(obj)
        return company.pincode if company else ""

    def get_company_contacts(self, obj):
        company = self._get_related_company(obj)
        if not company:
            return []
        return [
            {
                "name": contact.name,
                "designation": contact.designation,
                "phone": contact.phone,
                "email": contact.email,
                "is_primary": contact.is_primary,
            }
            for contact in company.contacts.all()
            if contact.is_active
        ]

    @staticmethod
    def _get_related_company(obj):
        if obj.company_id:
            return obj.company
        opportunity = obj.opportunity
        if not opportunity:
            return None
        if opportunity.company_id:
            return opportunity.company
        try:
            return opportunity.lead.company
        except (Lead.DoesNotExist, AttributeError):
            return None

    def get_company_id(self, obj):
        if obj.company_id:
            return obj.company_id
        opportunity = obj.opportunity
        if opportunity is None:
            return None
        if opportunity.company_id:
            return opportunity.company_id
        try:
            lead = opportunity.lead
        except Lead.DoesNotExist:
            lead = None
        return lead.company_id if lead else None

    def get_company_city(self, obj):
        if obj.company_id:
            return obj.company.city.name if obj.company.city_id else ""
        opportunity = obj.opportunity
        company = opportunity.company if opportunity else None
        if company and company.city:
            return company.city.name
        if opportunity and opportunity.lead and opportunity.lead.company and opportunity.lead.company.city:
            return opportunity.lead.company.city.name
        return ""

    def get_company_state(self, obj):
        company = obj.company
        opportunity = obj.opportunity
        if company is None and opportunity:
            company = opportunity.company
            if company is None:
                try:
                    company = opportunity.lead.company
                except (Lead.DoesNotExist, AttributeError):
                    company = None
        return company.state.name if company and company.state_id else ""

    def validate(self, attrs):
        if attrs.get("discount", 0) < 0:
            raise serializers.ValidationError({"discount": "Discount cannot be negative."})
        if attrs.get("tax_percentage", 0) < 0:
            raise serializers.ValidationError({"tax_percentage": "Tax percentage cannot be negative."})
        return attrs

    def validate_cpo_document(self, uploaded_document):
        if uploaded_document is None:
            return uploaded_document
        from django.conf import settings

        maximum_size = getattr(settings, "CPO_MAX_UPLOAD_SIZE", 10 * 1024 * 1024)
        if uploaded_document.size > maximum_size:
            raise serializers.ValidationError(
                f"PDF must not exceed {maximum_size // (1024 * 1024)} MB."
            )
        if not uploaded_document.name.lower().endswith(".pdf"):
            raise serializers.ValidationError("Only PDF documents are allowed.")
        header = uploaded_document.read(5)
        uploaded_document.seek(0)
        if header != b"%PDF-":
            raise serializers.ValidationError("The uploaded file is not a valid PDF.")
        return uploaded_document

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        selected_company = validated_data.pop("selected_company_id", None)
        if selected_company is not None:
            validated_data["company"] = selected_company
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise serializers.ValidationError({"created_by": "An authenticated user is required."})
        quotation = Quotation.objects.create(created_by=user, **validated_data)
        for item_data in items_data:
            QuotationItem.objects.create(quotation=quotation, **item_data)
        return quotation

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        selected_company = validated_data.pop("selected_company_id", None)
        quotation = super().update(instance, validated_data)
        if selected_company is not None:
            quotation.company = selected_company
            quotation.save(update_fields=["company", "updated_at"])
        if items_data is not None:
            quotation.items.all().delete()
            for item_data in items_data:
                QuotationItem.objects.create(quotation=quotation, **item_data)
        return quotation
      

class SalesOrderSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)
    company_address = serializers.CharField(source="company.address", read_only=True)
    company_city = serializers.IntegerField(source="company.city_id", read_only=True, allow_null=True)
    company_city_name = serializers.CharField(source="company.city.name", read_only=True, allow_null=True)
    company_state = serializers.IntegerField(source="company.state_id", read_only=True, allow_null=True)
    company_state_name = serializers.CharField(source="company.state.name", read_only=True, allow_null=True)
    company_country = serializers.IntegerField(source="company.country_id", read_only=True, allow_null=True)
    company_country_name = serializers.CharField(source="company.country.name", read_only=True, allow_null=True)
    company_pincode = serializers.CharField(source="company.pincode", read_only=True)
    company_gst_number = serializers.CharField(source="company.gst_number", read_only=True)
    quotation_number = serializers.CharField(source="quotation.quotation_number", read_only=True)
    project_name = serializers.CharField(source="quotation.project_name", read_only=True)
    items = QuotationItemSerializer(source="quotation.items", many=True, read_only=True)
    company_contacts = serializers.SerializerMethodField()
    quotation_pdf = serializers.FileField(source="quotation.quotation_pdf", read_only=True, use_url=True)
    final_offer_pdf = serializers.FileField(source="quotation.final_offer_pdf", read_only=True, use_url=True)
    cpo_document = serializers.FileField(source="quotation.cpo_document", read_only=True, use_url=True)
    created_by_name = serializers.SerializerMethodField()

    def get_company_contacts(self, obj):
        return CompanyContactSerializer(
            obj.company.contacts.filter(is_active=True), many=True
        ).data

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return ""
        return obj.created_by.get_full_name() or obj.created_by.get_username()

    class Meta:
        model = SalesOrder
        fields = [
            "id",
            "so_number",
            "so_date",
            "quotation",
            "quotation_number",
            "company",
            "company_name",
            "company_address",
            "company_city",
            "company_city_name",
            "company_state",
            "company_state_name",
            "company_country",
            "company_country_name",
            "company_pincode",
            "company_gst_number",
            "project_name",
            "subtotal",
            "discount_percentage",
            "discount_amount",
            "taxable_amount",
            "tax_percentage",
            "tax_amount",
            "cgst_amount",
            "sgst_amount",
            "igst_amount",
            "packing_charges",
            "total_amount",
            "tax_type",
            "payment_terms",
            "delivery_terms",
            "remarks",
            "status",
            "created_by",
            "created_by_name",
            "created_at",
            "items",
            "company_contacts",
            "quotation_pdf",
            "final_offer_pdf",
            "cpo_document",
            "so_pdf",
        ]
        read_only_fields = [
            "quotation",
            "company",
            "subtotal",
            "discount_percentage",
            "discount_amount",
            "taxable_amount",
            "tax_percentage",
            "tax_amount",
            "cgst_amount",
            "sgst_amount",
            "igst_amount",
            "packing_charges",
            "total_amount",
            "tax_type",
            "created_by",
            "created_by_name",
            "created_at",
            "items",
            "company_name",
            "company_address",
            "company_city",
            "company_city_name",
            "company_state",
            "company_state_name",
            "company_country",
            "company_country_name",
            "company_pincode",
            "company_gst_number",
            "quotation_number",
            "project_name",
            "company_contacts",
            "quotation_pdf",
            "final_offer_pdf",
            "cpo_document",
            "so_pdf",
        ]


# Task Serializers

class TaskSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    module_display = serializers.CharField(source='get_module_display', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True, allow_null=True, default=None)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    repeat_frequency_display = serializers.CharField(source='get_repeat_frequency_display', read_only=True)
    parent_task_title = serializers.CharField(source='parent_task.title', read_only=True)
    recurring_instances_count = serializers.SerializerMethodField()
    followup_history = serializers.JSONField(read_only=True)
    attachments = serializers.SerializerMethodField()

    def get_assigned_to_name(self, obj):
        return obj.assigned_to.get_full_name() or obj.assigned_to.get_username() if obj.assigned_to else None

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() or obj.created_by.get_username() if obj.created_by else None

    def get_attachments(self, obj):
        request = self.context.get('request')
        attachments = []
        for attachment in obj.attachments.all():
            file_url = attachment.file.url if attachment.file else None
            if file_url and request:
                file_url = request.build_absolute_uri(file_url)
            attachments.append({
                'id': attachment.id,
                'file_name': attachment.file_name,
                'file_url': file_url,
            })
        return attachments

    def get_recurring_instances_count(self, obj):
        if obj.is_recurring:
            return obj.recurring_instances.count()
        return 0

    def validate(self, data):
        task_regarding = data.get('task_regarding', getattr(self.instance, 'task_regarding', ''))
        reference_id = data.get('reference_id', getattr(self.instance, 'reference_id', ''))
        if task_regarding and task_regarding.upper() != 'MISCELLANEOUS' and not reference_id:
            raise serializers.ValidationError({
                'reference_id': 'Reference ID is required unless the task is miscellaneous.'
            })
        return data

    class Meta:
        model = Task
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'created_by']


class TaskAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskAttachment
        fields = ['id', 'file', 'file_name']


class TaskCreateSerializer(serializers.ModelSerializer):
    attachments = TaskAttachmentSerializer(many=True, read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = Task
        fields = [
            'title', 'description', 'module', 'reference_id',
            'followup_date', 'priority', 'assigned_to',
            'remarks', 'attachments', 'company', 'company_name', 'task_regarding',
            'is_recurring', 'repeat_frequency', 'repeat_interval', 'repeat_end_date'
        ]
