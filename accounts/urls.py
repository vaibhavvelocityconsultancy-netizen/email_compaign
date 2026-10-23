from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CurrentUserView,
    GoogleAuthorizationView,
    GoogleCallbackView,
    LoginView,
    LogoutView,
    ModuleViewSet,
    RefreshView,
    RegisterView,
    RolePermissionViewSet,
    RoleViewSet,
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
    path("google/authorize/", GoogleAuthorizationView.as_view(), name="google-authorize"),
    path("google/callback/", GoogleCallbackView.as_view(), name="google-callback"),
] + router.urls
