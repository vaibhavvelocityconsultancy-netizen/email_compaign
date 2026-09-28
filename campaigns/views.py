from django.forms import models
from django.shortcuts import render
from django.views import View
from rest_framework.response import Response
from rest_framework import viewsets, status

from rest_framework.decorators import action

# Create your views here.

import csv

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from campaigns.serializers import (
    BatchLeadSerializer,
    BatchSerializer,
    EmailSequenceSerializer,
    EmailSequenceStepSerializer,
    EmailTemplateSerializer,
    LeadSerializer,
)

from .models import Batch, EmailSequence, EmailSequenceStep, EmailTemplate, Lead


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

            required_columns = {
                "name",
                "email",
                "company",
                "phone",
                "source",
                "status",
            }

            csv_columns = set(reader.fieldnames or [])

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

            valid_sources = dict(Lead.SOURCE_CHOICES)
            valid_statuses = dict(Lead.STATUS_CHOICES)

            for row in reader:
                total_rows += 1

                name = (row.get("name") or "").strip()
                email = (row.get("email") or "").strip().lower()
                company = (row.get("company") or "").strip()
                phone = (row.get("phone") or "").strip()
                source = (row.get("source") or "").strip()
                lead_status = (row.get("status") or "").strip()

                # Basic validation
                if not name or not email or not company or not phone:
                    invalid += 1
                    continue

                # Validate source
                if source not in valid_sources:
                    invalid += 1
                    continue

                # Validate status
                if lead_status not in valid_statuses:
                    invalid += 1
                    continue

                # Duplicate email
                if Lead.objects.filter(email=email).exists():
                    duplicates += 1
                    continue

                Lead.objects.create(
                    name=name,
                    email=email,
                    company=company,
                    phone=phone,
                    source=source,
                    status=lead_status,
                )

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
                
                

class LeadListView(APIView):

    def get(self, request):
        leads = Lead.objects.all().order_by("-created_at")
        serializer = LeadSerializer(leads, many=True)

        return Response(
            {
                "count": leads.count(),
                "results": serializer.data
            },
            status=status.HTTP_200_OK
        )
        


class EmailTemplateViewSet(viewsets.ModelViewSet):
    queryset = EmailTemplate.objects.all()
    serializer_class = EmailTemplateSerializer
    
    def perform_create(self, serializer):
         serializer.save()
        #  logger.info(f"Email template '{serializer.instance.name}' created by user '{self.request.user.username}'.")
        
        
class EmailSequenceViewSet(viewsets.ModelViewSet):
    queryset = EmailSequence.objects.all()
    serializer_class = EmailSequenceSerializer
    
    def perform_create(self, serializer):
        serializer.save()
        # logger.info(f"Email sequence '{serializer.instance.name}' created by user '{self.request.user.username}'.")
        
        
class EmailSequenceStepViewSet(viewsets.ModelViewSet):
    queryset = EmailSequenceStep.objects.all()
    serializer_class = EmailSequenceStepSerializer
    
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


