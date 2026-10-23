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
    LeadSampleDataView,
    InboundReplyDetailView,
    InboundReplyListView,
    create_sales_order_from_quotation,
    lead_convert_to_opportunity,
    OpportunityDetailView,
    OpportunityListCreateView,
    OpportunityModuleDetailView,
    OpportunityModuleListCreateView,
    ConvertOpportunityToQuotationView,
    NextQuotationNumberView,
    QuotationDetailView,
    QuotationListCreateView,
    GenerateFinalOfferView,
    SalesOrderListView,
    SalesOrderDetailView,
    get_order_dashboard,
    UpdateFinalOfferView,
    StateViewSet,
    TaskDetailView,
    TaskListCreateView,
    TaskOptionsView,
    get_task_dashboard,
    get_activities,
    mailgun_inbound_webhook,
    mailgun_webhook,
    campaign_unsubscribe,
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
        "leads/sample-data/",
        LeadSampleDataView.as_view(),
        name="lead-sample-data",
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
        "leads/<int:lead_id>/convert-to-opportunity/",
        lead_convert_to_opportunity,
        name="lead-convert-to-opportunity",
    ),
    path(
        "opportunities/",
        OpportunityListCreateView.as_view(),
        name="opportunity-list",
    ),
    path(
        "opportunities/<int:pk>/",
        OpportunityDetailView.as_view(),
        name="opportunity-detail",
    ),
    path(
        "opportunities/<int:opportunity_id>/modules/",
        OpportunityModuleListCreateView.as_view(),
        name="opportunity-module-list",
    ),
    path(
        "opportunities/<int:opportunity_id>/modules/<int:pk>/",
        OpportunityModuleDetailView.as_view(),
        name="opportunity-module-detail",
    ),
    path(
        "opportunities/<int:pk>/convert-to-quotation/",
        ConvertOpportunityToQuotationView.as_view(),
        name="opportunity-convert-to-quotation",
    ),
    path(
        "quotations/",
        QuotationListCreateView.as_view(),
        name="quotation-list",
    ),
    path(
        "quotations/next-number/",
        NextQuotationNumberView.as_view(),
        name="quotation-next-number",
    ),
    path(
        "quotations/<int:pk>/",
        QuotationDetailView.as_view(),
        name="quotation-detail",
    ),
    path(
        "quotations/<int:pk>/generate-final-offer/",
        GenerateFinalOfferView.as_view(),
        name="quotation-generate-final-offer",
    ),
    path(
        "quotations/<int:pk>/final-offer/",
        UpdateFinalOfferView.as_view(),
        name="quotation-final-offer-update",
    ),
    path(
        "create-sales/<int:quotation_id>/",
        create_sales_order_from_quotation,
        name="create-sales-order-from-quotation",
    ),
    path(
        "sales-orders/",
        SalesOrderListView.as_view(),
        name="sales-order-list",
    ),
    path(
        "sales-orders/<int:pk>/",
        SalesOrderDetailView.as_view(),
        name="sales-order-detail",
    ),
    path("order-dashboard/", get_order_dashboard, name="order-dashboard"),
    path("tasks/", TaskListCreateView.as_view(), name="task-list-create"),
    path("tasks/dashboard/", get_task_dashboard, name="task-dashboard"),
    path("tasks/activities/", get_activities, name="task-activities"),
    path("tasks/<int:pk>/", TaskDetailView.as_view(), name="task-detail"),
    path("task-options/", TaskOptionsView.as_view(), name="task-options"),
    path(
        "email-logs/",
        EmailLogListView.as_view(),
        name="email-log-list",
    ),
    path(
        "inbound-replies/",
        InboundReplyListView.as_view(),
        name="inbound-reply-list",
    ),
    path(
        "inbound-replies/<int:pk>/",
        InboundReplyDetailView.as_view(),
        name="inbound-reply-detail",
    ),
      path(
          "email/unsubscribe/<str:token>/",
          campaign_unsubscribe,
          name="campaign-unsubscribe",
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