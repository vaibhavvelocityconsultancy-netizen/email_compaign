from django.forms import models
from django.shortcuts import render
from django.views import View
from rest_framework.response import Response
from rest_framework import generics, viewsets, status

from rest_framework.decorators import action

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
from django.contrib.auth import get_user_model
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt



from campaigns.serializers import (
    BatchLeadSerializer,
    BatchSerializer,
    MessageLogSerializer,
    SequenceSerializer,
    SequenceStepSerializer,
    MessageTemplateSerializer,
    LeadSerializer,
)

from .models import Batch, BatchLead, Channel, MessageLog, Sequence, SequenceStep, MessageTemplate, Lead


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
            required_columns = {"enquiry_for", "enquiry_date", "lead_received_by", "source"}
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
                received_user = self.resolve_user(row.get("lead_received_by"))
                assigned_user = self.resolve_user(row.get("lead_assign_to")) if row.get("lead_assign_to") else None
                if not received_user or (row.get("lead_assign_to") and not assigned_user):
                    invalid += 1
                    continue

                data = {
                    "enquiry_for": (row.get("enquiry_for") or "").strip().upper(),
                    "enquiry_date": (row.get("enquiry_date") or "").strip(),
                    "lead_received_by": received_user.pk,
                    "lead_assign_to": assigned_user.pk if assigned_user else None,
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

    @staticmethod
    def resolve_user(identifier):
        if not identifier:
            return None
        users = get_user_model().objects.filter(is_active=True)
        value = identifier.strip()
        if value.isdigit():
            return users.filter(pk=int(value)).first()
        return users.filter(username=value).first()
                
                

class LeadListView(APIView):

    def get(self, request):
        leads = Lead.objects.filter(is_active=True).select_related(
            "lead_received_by", "lead_assign_to"
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
    queryset = Lead.objects.filter(is_active=True).select_related(
        "lead_received_by", "lead_assign_to"
    )
    serializer_class = LeadSerializer

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])


class LeadUserListView(APIView):
    def get(self, request):
        users = get_user_model().objects.filter(is_active=True).order_by("first_name", "last_name", "username")
        return Response([
            {
                "id": user.pk,
                "name": user.get_full_name() or user.get_username(),
            }
            for user in users
        ])


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

@csrf_exempt
def mailgun_webhook(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST method required"},
            status=405
        )

    try:
        data = json.loads(request.body)

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