from decimal import Decimal, InvalidOperation

from django.forms import models
from django.shortcuts import get_object_or_404, render
from django.db.models import Count, Q
from django.views import View
from rest_framework.response import Response
from rest_framework import generics, viewsets, status

from rest_framework.decorators import action, api_view
from rest_framework.permissions import IsAuthenticated

# Create your views here.

import csv
import hashlib
import hmac
import re
from datetime import datetime, timezone as dt_timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import json

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt



from campaigns.serializers import (
    BatchLeadSerializer,
    BatchSerializer,
    CitySerializer,
    CompanyContactSerializer,
    CompanySerializer,
    CountrySerializer,
    MessageLogSerializer,
    SequenceSerializer,
    SequenceStepSerializer,
    StateSerializer,
    MessageTemplateSerializer,
    LeadSerializer,
    OpportunityCreateSerializer,
    OpportunityModuleSerializer,
    QuotationSerializer,
)

from .models import Batch, BatchLead, Channel, City, Company, CompanyContact, Country, MessageLog, Opportunity, OpportunityModule, Quotation, QuotationItem, Sequence, SequenceStep, State, MessageTemplate, Lead

# ------------------------------------- masters ----------------------


# company 

class CountryViewSet(viewsets.ModelViewSet):
    queryset = Country.objects.all()
    serializer_class = CountrySerializer


class StateViewSet(viewsets.ModelViewSet):
    queryset = State.objects.all()
    serializer_class = StateSerializer


class CityViewSet(viewsets.ModelViewSet):
    queryset = City.objects.all()
    serializer_class = CitySerializer


class CompanyListView(APIView):
    def get(self, request):
        companies = Company.objects.filter(is_active=True).annotate(
            contacts_count=Count("contacts", filter=Q(contacts__is_active=True))
        ).order_by("name")
        return Response({
            "count": companies.count(),
            "results": CompanySerializer(companies, many=True).data,
        })

    def post(self, request):
        serializer = CompanySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = serializer.save()
        company.contacts_count = 0
        return Response(CompanySerializer(company).data, status=status.HTTP_201_CREATED)


class CompanyDetailView(generics.RetrieveUpdateAPIView):
    queryset = Company.objects.filter(is_active=True).annotate(
        contacts_count=Count("contacts", filter=Q(contacts__is_active=True))
    )
    serializer_class = CompanySerializer


class CompanyContactListCreateView(APIView):
    def get(self, request, company_id):
        company = get_object_or_404(Company, pk=company_id, is_active=True)
        contacts = company.contacts.filter(is_active=True).order_by("-is_primary", "name")
        return Response(CompanyContactSerializer(contacts, many=True).data)

    def post(self, request, company_id):
        company = get_object_or_404(Company, pk=company_id, is_active=True)
        serializer = CompanyContactSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            CompanyContactSerializer(serializer.save(company=company)).data,
            status=status.HTTP_201_CREATED,
        )


class CompanyContactDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CompanyContactSerializer

    def get_queryset(self):
        return CompanyContact.objects.filter(
            company_id=self.kwargs["company_id"],
            company__is_active=True,
            is_active=True,
        )

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])


class LeadCSVImportView(APIView):
    def post(self, request):
        csv_file = request.FILES.get("file")

        if not csv_file:
            return Response(
                {"error": "CSV file is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not csv_file.name.lower().endswith(".csv"):
            return Response(
                {"error": "Only CSV files are allowed."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            decoded_file = csv_file.read().decode("utf-8-sig").splitlines()
            reader = csv.DictReader(decoded_file)

            csv_columns = set(reader.fieldnames or [])
            required_columns = {"company_name", "enquiry_for", "enquiry_date", "source"}
            missing_columns = required_columns - csv_columns

            if missing_columns:
                return Response(
                    {
                        "error": "Missing required columns.",
                        "missing_columns": list(missing_columns),
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            total_rows = 0
            imported = 0
            duplicates = 0
            invalid = 0

            for row in reader:
                total_rows += 1
                data = {
                    "company_name": (row.get("company_name") or "").strip(),
                    "company_address": (row.get("company_address") or "").strip(),
                    "company_city": (row.get("company_city") or "").strip(),
                    "company_state": (row.get("company_state") or "").strip(),
                    "company_pincode": (row.get("company_pincode") or "").strip(),
                    "company_country": (row.get("company_country") or "India").strip(),
                    "company_gst_number": (row.get("company_gst_number") or "").strip(),
                    "contact_name": (row.get("contact_name") or "").strip(),
                    "contact_designation": (row.get("contact_designation") or "").strip(),
                    "contact_mobile": (row.get("contact_mobile") or "").strip(),
                    "contact_email": (row.get("contact_email") or "").strip(),
                    "enquiry_for": (row.get("enquiry_for") or "").strip().upper(),
                    "enquiry_date": (row.get("enquiry_date") or "").strip(),
                    "source": (row.get("source") or "").strip().upper(),
                    "status": (row.get("status") or "NEW").strip().upper(),
                    "followup_date": (row.get("followup_date") or "").strip() or None,
                    "followup_remarks": (row.get("followup_remarks") or "").strip(),
                    "is_opportunity": (row.get("is_opportunity") or "").strip().lower() in {"1", "true", "yes", "y"},
                }
                serializer = LeadSerializer(data=data)
                if not serializer.is_valid():
                    invalid += 1
                    continue
                serializer.save()
                imported += 1

            return Response(
                {
                    "message": "CSV imported successfully.",
                    "total_rows": total_rows,
                    "imported": imported,
                    "duplicates": duplicates,
                    "invalid": invalid,
                },
                status=status.HTTP_201_CREATED
            )

        except UnicodeDecodeError:
            return Response(
                {"error": "CSV must be UTF-8 encoded."},
                status=status.HTTP_400_BAD_REQUEST
            )

class LeadOptionsView(APIView):
    def get(self, request):
        def to_options(choices):
            return [{"value": value, "label": label} for value, label in choices]

        return Response(
            {
                "enquiry_for": to_options(Lead.ENQUIRY_FOR_CHOICES),
                "source": to_options(Lead.SOURCE_CHOICES),
                "status": to_options(Lead.STATUS_CHOICES),
            },
            status=status.HTTP_200_OK,
        )


class LeadListView(APIView):

    def get(self, request):
        leads = Lead.objects.filter(is_active=True, is_opportunity=False).select_related(
            "company", "contact"
        ).order_by("-enquiry_date", "-created_at")
        serializer = LeadSerializer(leads, many=True)

        return Response(
            {
                "count": leads.count(),
                "results": serializer.data
            },
            status=status.HTTP_200_OK
        )

    def post(self, request):
        serializer = LeadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class LeadDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Lead.objects.filter(is_active=True).select_related("company", "contact")
    serializer_class = LeadSerializer

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])


class OpportunityListCreateView(generics.ListCreateAPIView):
    queryset = Opportunity.objects.filter(is_active=True).prefetch_related("modules")
    serializer_class = OpportunityCreateSerializer


class OpportunityDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Opportunity.objects.filter(is_active=True).prefetch_related("modules")
    serializer_class = OpportunityCreateSerializer 

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


class OpportunityModuleListCreateView(generics.ListCreateAPIView):
    serializer_class = OpportunityModuleSerializer

    def get_opportunity(self):
        return get_object_or_404(
            Opportunity,
            pk=self.kwargs["opportunity_id"],
            is_active=True,
        )

    def get_queryset(self):
        return OpportunityModule.objects.filter(
            opportunity_id=self.kwargs["opportunity_id"],
            opportunity__is_active=True,
        ).order_by("module_number")
        

    def perform_create(self, serializer):
        opportunity = self.get_opportunity()
        module_number = serializer.validated_data.get("module_number")
        if module_number is None:
            last_number = opportunity.modules.order_by("-module_number").values_list(
                "module_number", flat=True
            ).first()
            module_number = (last_number or 0) + 1
        serializer.save(opportunity=opportunity, module_number=module_number)


class OpportunityModuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = OpportunityModuleSerializer

    def get_queryset(self):
        return OpportunityModule.objects.filter(
            opportunity_id=self.kwargs["opportunity_id"],
            opportunity__is_active=True,
        )


class QuotationListCreateView(generics.ListCreateAPIView):
    queryset = (
        Quotation.objects
        .select_related("opportunity", "created_by")
        .prefetch_related("items__module")
        .all()
    )
    serializer_class = QuotationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        opportunity_id = self.request.query_params.get("opportunity")
        search = self.request.query_params.get("search")

        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if opportunity_id:
            queryset = queryset.filter(opportunity_id=opportunity_id)
        if search:
            queryset = queryset.filter(
                Q(quotation_number__icontains=search)
                | Q(opportunity__enquiry_for__icontains=search)
            )
        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save()


class QuotationDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = (
        Quotation.objects
        .select_related("opportunity", "created_by")
        .prefetch_related("items__module")
        .all()
    )
    serializer_class = QuotationSerializer
    permission_classes = [IsAuthenticated]


class GenerateFinalOfferView(generics.GenericAPIView):
    queryset = Quotation.objects.all()
    serializer_class = QuotationSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        quotation = self.get_object()
        quotation.final_offer_generated = True
        quotation.save(update_fields=["final_offer_generated", "updated_at"])
        return Response(self.get_serializer(quotation).data, status=status.HTTP_200_OK)


class EmailLogListView(APIView):
    def get(self, request):
        logs = MessageLog.objects.select_related(
            "batch_lead", "template"
        ).order_by("-sent_at")
        serializer = MessageLogSerializer(logs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
        


class EmailTemplateViewSet(viewsets.ModelViewSet):
    queryset = MessageTemplate.objects.all()
    serializer_class = MessageTemplateSerializer
    
    def perform_create(self, serializer):
         serializer.save()
        #  logger.info(f"Email template '{serializer.instance.name}' created by user '{self.request.user.username}'.")
        
        
class EmailSequenceViewSet(viewsets.ModelViewSet):
    queryset = Sequence.objects.all()
    serializer_class = SequenceSerializer
    
    def perform_create(self, serializer):
        serializer.save()
        # logger.info(f"Email sequence '{serializer.instance.name}' created by user '{self.request.user.username}'.")
        
        
class EmailSequenceStepViewSet(viewsets.ModelViewSet):
    queryset = SequenceStep.objects.all()
    serializer_class = SequenceStepSerializer
    
    def perform_create(self, serializer):
        serializer.save()
        # logger.info(f"Email sequence step '{serializer.instance.step_number}' for sequence '{serializer.instance.sequence.name}' created by user '{self.request.user.username}'.")
        
        
class BatchViewSet(viewsets.ModelViewSet):
    queryset = Batch.objects.all()
    serializer_class = BatchSerializer
    
    def perform_create(self, serializer):
        serializer.save()
        
        
    @action(detail=True, methods=['get'], url_path='leads')
    def get_batch_leads(self, request, pk=None):
        batch = self.get_object()
        leads = batch.batch_leads.all()
        serializer = BatchLeadSerializer(leads, many=True)
        return Response(serializer.data)
        

    @action(detail=True, methods=['patch'], url_path='pause', url_name='pause')
    def pause_batch(self, request, pk=None):
        batch = self.get_object()
        batch.status = Batch.Status.PAUSED
        batch.save()
        return Response({"status": "Batch paused."}, status=status.HTTP_200_OK)
    
    
    @action(detail=True, methods=['patch'], url_path='resume')
    def resume(self, request, pk=None):
        batch = self.get_object()
        batch.status = Batch.Status.ACTIVE
        batch.save(update_fields=['status'])
        return Response({'status': batch.status}, status=status.HTTP_200_OK)




# webhook

def _is_valid_mailgun_signature(signature_data):
    signing_key = getattr(settings, "ANYMAIL", {}).get("MAILGUN_WEBHOOK_SIGNING_KEY", "")
    timestamp = str(signature_data.get("timestamp", ""))
    token = str(signature_data.get("token", ""))
    signature = str(signature_data.get("signature", ""))

    if not signing_key or not timestamp or not token or not signature:
        return False

    expected_signature = hmac.new(
        signing_key.encode(),
        f"{timestamp}{token}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)


@csrf_exempt
def mailgun_webhook(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST method required"},
            status=405
        )

    try:
        data = json.loads(request.body)
        if not _is_valid_mailgun_signature(data.get("signature", {})):
            return JsonResponse({"error": "Webhook signature is invalid."}, status=403)

        event_data = data.get("event-data", {})

        event = event_data.get("event")
        recipient = event_data.get("recipient", "").strip().lower()

        print("Mailgun Event:", event)
        print("Recipient:", recipient)

        # Mailgun event → MessageLog status
        event_status_map = {
            "accepted": MessageLog.Status.ACCEPTED,
            "delivered": MessageLog.Status.DELIVERED,
            "opened": MessageLog.Status.OPENED,
            "clicked": MessageLog.Status.CLICKED,
            "failed": MessageLog.Status.FAILED,
            "complained": MessageLog.Status.COMPLAINED,
            "unsubscribed": MessageLog.Status.UNSUBSCRIBED,
        }

        new_status = event_status_map.get(event)

        if not new_status:
            return JsonResponse({
                "status": "ignored",
                "event": event,
                "message": "Event is not handled"
            })

        message_id = event_data.get("message", {}).get("headers", {}).get("message-id", "")
        message_id = message_id.strip().strip("<>").lower()
        email_log = MessageLog.objects.filter(
            channel=Channel.EMAIL,
            provider_message_id=message_id,
        ).first() if message_id else None

        # Fall back to recipient for legacy events without a message ID.
        if not email_log:
            email_log = (
                MessageLog.objects
                .filter(channel=Channel.EMAIL, to_address__iexact=recipient)
                .order_by("-sent_at")
                .first()
            )

        if not email_log:
            print("MessageLog not found for:", recipient)

            return JsonResponse({
                "status": "not_found",
                "event": event,
                "recipient": recipient
            })

        # Update status
        email_log.status = new_status
        email_log.save(update_fields=["status"])

        print(
            f"MessageLog {email_log.id} updated: "
            f"{recipient} → {new_status}"
        )

        # If unsubscribed, also update BatchLead
        if event == "unsubscribed":
            batch_lead = email_log.batch_lead

            batch_lead.unsubscribed = True
            batch_lead.save(update_fields=["unsubscribed"])

        return JsonResponse({
            "status": "updated",
            "event": event,
            "recipient": recipient,
            "email_log_id": email_log.id,
            "message_log_id": email_log.id,
            "message_status": new_status,
        })

    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "error": "Invalid JSON payload"
        }, status=400)

    except Exception as e:
        print("Mailgun webhook error:", str(e))

        return JsonResponse({
            "status": "error",
            "error": str(e),
        }, status=400)
        
@csrf_exempt
def mailgun_inbound_webhook(request):
    if request.method != "POST":
        return JsonResponse(
            {"error": "POST method required"},
            status=405
        )

    signature_data = {
        "timestamp": request.POST.get("timestamp", ""),
        "token": request.POST.get("token", ""),
        "signature": request.POST.get("signature", ""),
    }
    if not _is_valid_mailgun_signature(signature_data):
        return JsonResponse({"error": "Webhook signature is invalid."}, status=403)

    try:
        sender = request.POST.get("sender", "").strip().lower()
        subject = request.POST.get("subject", "")
        body = request.POST.get("body-plain", "")

        print("Mailgun Reply Received")
        print("Sender:", sender)
        print("Subject:", subject)
        print("Body:", body)

        # Find the lead who replied
        batch_lead = BatchLead.objects.filter(
            email__iexact=sender
        ).first()

        if not batch_lead:
            return JsonResponse({
                "status": "ignored",
                "message": "No matching lead found",
                "sender": sender
            })

        # Mark lead as replied
        batch_lead.replied = True
        batch_lead.replied_at = timezone.now()

        # Stop future emails
        batch_lead.save(
            update_fields=["replied", "replied_at"]
        )

        # Update latest email log
        latest_log = MessageLog.objects.filter(
            batch_lead=batch_lead,
            channel=Channel.EMAIL,
        ).order_by("-sent_at").first()

        if latest_log:
            latest_log.status = MessageLog.Status.REPLIED
            latest_log.save(update_fields=["status"])

        return JsonResponse({
            "status": "updated",
            "sender": sender,
            "batch_lead_id": batch_lead.id,
            "email_log_id": latest_log.id if latest_log else None,
            "message_log_id": latest_log.id if latest_log else None
        })

    except Exception as e:
        return JsonResponse({
            "status": "error",
            "error": str(e)
        }, status=400)


@csrf_exempt
def whatsapp_webhook(request):
    verify_token = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "")

    if request.method == "GET":
        mode = request.GET.get("hub.mode", "")
        token = request.GET.get("hub.verify_token", "")
        challenge = request.GET.get("hub.challenge", "")
        if mode == "subscribe" and verify_token and hmac.compare_digest(token, verify_token):
            return HttpResponse(challenge, content_type="text/plain")
        return JsonResponse({"error": "Webhook verification failed."}, status=403)

    if request.method != "POST":
        return JsonResponse({"error": "GET or POST method required."}, status=405)

    app_secret = getattr(settings, "WHATSAPP_APP_SECRET", "")
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected_signature = "sha256=" + hmac.new(
        app_secret.encode(), request.body, hashlib.sha256
    ).hexdigest() if app_secret else ""
    if not expected_signature or not hmac.compare_digest(signature, expected_signature):
        return JsonResponse({"error": "Webhook signature is invalid."}, status=403)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    status_map = {
        "sent": MessageLog.Status.SENT,
        "delivered": MessageLog.Status.DELIVERED,
        "read": MessageLog.Status.READ,
        "failed": MessageLog.Status.FAILED,
    }
    status_rank = {
        MessageLog.Status.SENT: 1,
        MessageLog.Status.FAILED: 2,
        MessageLog.Status.DELIVERED: 3,
        MessageLog.Status.READ: 4,
    }
    updated = 0
    replied = 0

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for provider_status in value.get("statuses", []):
                provider_message_id = provider_status.get("id", "")
                new_status = status_map.get(provider_status.get("status"))
                if not provider_message_id or not new_status:
                    continue
                message_log = MessageLog.objects.filter(
                    channel=Channel.WHATSAPP,
                    provider_message_id=provider_message_id,
                ).first()
                if not message_log:
                    continue
                if status_rank[new_status] < status_rank.get(message_log.status, 0):
                    continue
                errors = provider_status.get("errors", [])
                message_log.status = new_status
                message_log.error = (
                    errors[0].get("title") or errors[0].get("message", "")
                ) if new_status == MessageLog.Status.FAILED and errors else ""
                message_log.save(update_fields=["status", "error"])
                updated += 1

            for inbound_message in value.get("messages", []):
                sender = re.sub(r"\D", "", inbound_message.get("from", ""))
                if not sender:
                    continue
                batch_lead = BatchLead.objects.filter(
                    phone__in=[sender, f"+{sender}"],
                    replied=False,
                    message_logs__channel=Channel.WHATSAPP,
                ).distinct().first()
                if not batch_lead:
                    continue

                try:
                    replied_at = datetime.fromtimestamp(
                        float(inbound_message.get("timestamp")),
                        tz=dt_timezone.utc,
                    )
                except (TypeError, ValueError, OSError):
                    replied_at = timezone.now()
                batch_lead.replied = True
                batch_lead.replied_at = replied_at
                batch_lead.save(update_fields=["replied", "replied_at"])

                latest_log = MessageLog.objects.filter(
                    batch_lead=batch_lead,
                    channel=Channel.WHATSAPP,
                ).order_by("-sent_at").first()
                if latest_log:
                    latest_log.status = MessageLog.Status.REPLIED
                    latest_log.save(update_fields=["status"])
                replied += 1

    return JsonResponse({"status": "processed", "updated": updated, "replied": replied})
  
  

# convert to opportunity

@api_view(['POST'])
def lead_convert_to_opportunity(request, lead_id):
    lead = get_object_or_404(
        Lead,
        pk=lead_id,
        is_active=True
    )

    if lead.is_opportunity:
        return Response(
            {
                'error': 'Lead is already converted to an opportunity.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    opportunity = Opportunity.objects.create(
        lead=lead,
        company=lead.company,
        source=lead.source,
        status='PROSPECTING',
        is_converted_from_lead=True,
        converted_at=timezone.now(),
        converted_by=request.user if request.user.is_authenticated else None,
    )

    lead.is_opportunity = True
    lead.save(update_fields=['is_opportunity', 'updated_at'])

    return Response(
        {
            'message': 'Lead converted to opportunity successfully',
            'opportunity_id': opportunity.id,
            'is_opportunity': lead.is_opportunity,
            'is_converted_from_lead': opportunity.is_converted_from_lead,
            'company_name': lead.company.name,
        },
        status=status.HTTP_201_CREATED
    )
    
    
    # convert to quotaitn
def generate_quotation_number():
    year = timezone.now().year

    prefix = f"QT-{year}-"

    last_quotation = (
        Quotation.objects
        .filter(quotation_number__startswith=prefix)
        .order_by("-id")
        .first()
    )

    if last_quotation:
        try:
            last_number = int(
                last_quotation.quotation_number.replace(prefix, "")
            )
        except ValueError:
            last_number = 0
    else:
        last_number = 0

    return f"{prefix}{last_number + 1:04d}"

class ConvertOpportunityToQuotationView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        opportunity = (
            Opportunity.objects
            .prefetch_related("modules")
            .select_related("company", "lead")
            .filter(id=pk, is_active=True)
            .first()
        )

        if opportunity is None:
            return Response({"detail": "Opportunity not found."}, status=status.HTTP_404_NOT_FOUND)

        modules = list(opportunity.modules.all().order_by("module_number"))
        if not modules:
            return Response({"detail": "Cannot convert opportunity without modules."}, status=status.HTTP_400_BAD_REQUEST)

        if opportunity.quotations.filter(status__in=["DRAFT", "SENT", "APPROVED", "REVISION"]).exists():
            return Response({"detail": "An active quotation already exists for this opportunity."}, status=status.HTTP_400_BAD_REQUEST)

        raw_items = request.data.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            return Response({"detail": "At least one module item is required."}, status=status.HTTP_400_BAD_REQUEST)

        module_map = {module.id: module for module in modules}
        submitted_by_module = {}

        for index, raw_item in enumerate(raw_items, start=1):
            if not isinstance(raw_item, dict):
                return Response({"detail": f"Item {index} is invalid."}, status=status.HTTP_400_BAD_REQUEST)

            module_id = raw_item.get("module")
            amount_value = raw_item.get("amount")

            if module_id in (None, ""):
                return Response({"detail": f"Item {index} is missing a module reference."}, status=status.HTTP_400_BAD_REQUEST)

            try:
                module_id = int(module_id)
            except (TypeError, ValueError):
                return Response({"detail": f"Item {index} has an invalid module id."}, status=status.HTTP_400_BAD_REQUEST)

            if module_id not in module_map:
                return Response({"detail": f"Module {module_id} does not belong to this opportunity."}, status=status.HTTP_400_BAD_REQUEST)

            if module_id in submitted_by_module:
                return Response({"detail": f"Module {module_id} was submitted more than once."}, status=status.HTTP_400_BAD_REQUEST)

            if amount_value in (None, ""):
                return Response({"detail": f"Amount is required for module {module_id}."}, status=status.HTTP_400_BAD_REQUEST)

            try:
                amount = Decimal(str(amount_value))
            except InvalidOperation:
                return Response({"detail": f"Amount for module {module_id} must be numeric."}, status=status.HTTP_400_BAD_REQUEST)

            if amount < 0:
                return Response({"detail": f"Amount for module {module_id} cannot be negative."}, status=status.HTTP_400_BAD_REQUEST)

            submitted_by_module[module_id] = amount

        missing_modules = [module.id for module in modules if module.id not in submitted_by_module]
        if missing_modules:
            return Response({"detail": "All opportunity modules must be included in the request."}, status=status.HTTP_400_BAD_REQUEST)

        quotation = Quotation.objects.create(
            quotation_number=generate_quotation_number(),
            quotation_date=timezone.now().date(),
            opportunity=opportunity,
            project_name=(opportunity.project_name or "").strip(),
            status="DRAFT",
            discount=Decimal("0.00"),
            tax_type="",
            tax_percentage=Decimal("0.00"),
            packing_charges=Decimal("0.00"),
            terms_conditions="",
            delivery_timeline="",
            created_by=request.user,
        )

        subtotal = Decimal("0.00")
        for module in modules:
            amount = submitted_by_module[module.id]
            QuotationItem.objects.create(
                quotation=quotation,
                module=module,
                description=module.description or module.module_name,
                amount=amount,
            )
            subtotal += amount

        quotation.subtotal = subtotal
        quotation.taxable_amount = subtotal
        quotation.tax_amount = Decimal("0.00")
        quotation.cgst_amount = Decimal("0.00")
        quotation.sgst_amount = Decimal("0.00")
        quotation.igst_amount = Decimal("0.00")
        quotation.total_amount = subtotal
        quotation.save()

        serializer = QuotationSerializer(quotation)
        return Response({"message": "Opportunity converted to quotation successfully.", "quotation": serializer.data}, status=status.HTTP_201_CREATED)