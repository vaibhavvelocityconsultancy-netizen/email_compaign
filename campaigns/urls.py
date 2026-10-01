from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BatchViewSet,
    CityViewSet,
    CompanyContactDetailView,
    CompanyContactListCreateView,
    CompanyDetailView,
    CompanyListView,
    CountryViewSet,
    EmailLogListView,
    EmailSequenceStepViewSet,
    EmailSequenceViewSet,
    EmailTemplateViewSet,
    LeadCSVImportView,
    LeadDetailView,
    LeadListView,
    LeadOptionsView,
    StateViewSet,
    mailgun_inbound_webhook,
    mailgun_webhook,
    whatsapp_webhook,
)

router = DefaultRouter()
router.register("countries", CountryViewSet, basename="country")
router.register("states", StateViewSet, basename="state")
router.register("cities", CityViewSet, basename="city")
router.register("email-templates", EmailTemplateViewSet, basename="email-template")
router.register("email-sequences", EmailSequenceViewSet, basename="email-sequence")
router.register("sequence-steps", EmailSequenceStepViewSet, basename="sequence-step")
router.register("batches", BatchViewSet, basename="batch")

urlpatterns = [
    path("companies/", CompanyListView.as_view(), name="company-list"),
    path("companies/<int:pk>/", CompanyDetailView.as_view(), name="company-detail"),
    path(
        "companies/<int:company_id>/contacts/",
        CompanyContactListCreateView.as_view(),
        name="company-contact-list",
    ),
    path(
        "companies/<int:company_id>/contacts/<int:pk>/",
        CompanyContactDetailView.as_view(),
        name="company-contact-detail",
    ),
    path(
        "lead-options/",
        LeadOptionsView.as_view(),
        name="lead-options",
    ),
    path(
        "leads/import-csv/",
        LeadCSVImportView.as_view(),
        name="lead-csv-import",
    ),
    path(
        "leads/",
        LeadListView.as_view(),
        name="lead-list",
    ),
    path(
        "leads/<int:pk>/",
        LeadDetailView.as_view(),
        name="lead-detail",
    ),
    path(
        "email-logs/",
        EmailLogListView.as_view(),
        name="email-log-list",
    ),
      path(
        "webhooks/mailgun/",
        mailgun_webhook,
        name="mailgun-webhook"
    ),
      path(
        "webhooks/mailgun/inbound/",
        mailgun_inbound_webhook,
        name="mailgun-inbound-webhook"
    ),
    path(
        "webhooks/whatsapp/",
        whatsapp_webhook,
        name="whatsapp-webhook",
    ),
    path("", include(router.urls)),
]