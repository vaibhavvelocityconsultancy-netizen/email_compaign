from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BatchViewSet,
    EmailSequenceStepViewSet,
    EmailSequenceViewSet,
    EmailTemplateViewSet,
    LeadCSVImportView,
    LeadListView,
)

router = DefaultRouter()
router.register("email-templates", EmailTemplateViewSet, basename="email-template")
router.register("email-sequences", EmailSequenceViewSet, basename="email-sequence")
router.register("sequence-steps", EmailSequenceStepViewSet, basename="sequence-step")
router.register("batches", BatchViewSet, basename="batch")

urlpatterns = [
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
    path("", include(router.urls)),
]