from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CurrentUserView,
    GoogleAuthorizationView,
    GoogleCallbackView,
    GmailConnectionView,
    LoginView,
    LogoutView,
    ModuleViewSet,
    OwnTenantMailgunSettingsView,
    RefreshView,
    RegisterView,
    SystemLogAdminActionView,
    SystemLogAdminListView,
    SystemLogAdminMarkAllReadView,
    RolePermissionViewSet,
    RoleViewSet,
    TenantAdminDetailView,
    TenantAdminListView,
    TenantMailgunSettingsDetailView,
    TenantMailgunSettingsListView,
    UserViewSet,
)

app_name = "accounts"

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("roles", RoleViewSet, basename="role")
router.register("modules", ModuleViewSet, basename="module")
router.register("role-permissions", RolePermissionViewSet, basename="role-permission")

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("register/", RegisterView.as_view(), name="register"),
    path("refresh/", RefreshView.as_view(), name="refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", CurrentUserView.as_view(), name="me"),
    path(
        "mailgun-settings/",
        OwnTenantMailgunSettingsView.as_view(),
        name="own-mailgun-settings",
    ),
    path("mailgun-settings/tenants/", TenantMailgunSettingsListView.as_view(), name="mailgun-settings-tenants"),
    path(
        "mailgun-settings/tenants/<int:tenant_id>/",
        TenantMailgunSettingsDetailView.as_view(),
        name="mailgun-settings-detail",
    ),
    path("tenants/", TenantAdminListView.as_view(), name="tenant-admin-list"),
    path("tenants/<int:tenant_id>/", TenantAdminDetailView.as_view(), name="tenant-admin-detail"),
    path("system-logs/", SystemLogAdminListView.as_view(), name="system-log-admin-list"),
    path("system-logs/read-all/", SystemLogAdminMarkAllReadView.as_view(), name="system-log-mark-all-read"),
    path("system-logs/<int:log_id>/action/", SystemLogAdminActionView.as_view(), name="system-log-admin-action"),
    path("google/authorize/", GoogleAuthorizationView.as_view(), name="google-authorize"),
    path("google/callback/", GoogleCallbackView.as_view(), name="google-callback"),
    path("gmail-connection/", GmailConnectionView.as_view(), name="gmail-connection"),
] + router.urls
