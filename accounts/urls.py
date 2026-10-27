from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CurrentUserView,
    GoogleAuthorizationView,
    GoogleCallbackView,
    LoginView,
    LogoutView,
    ModuleViewSet,
    OwnTenantMailgunSettingsView,
    RefreshView,
    RegisterView,
    RolePermissionViewSet,
    RoleViewSet,
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
    path("google/authorize/", GoogleAuthorizationView.as_view(), name="google-authorize"),
    path("google/callback/", GoogleCallbackView.as_view(), name="google-callback"),
] + router.urls
