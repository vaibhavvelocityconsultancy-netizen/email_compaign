import hashlib
import hmac
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.db import models, transaction
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from campaigns.models import GmailMailbox

from .gmail_oauth import (
    GmailOAuthConfigurationError,
    GmailOAuthError,
    complete_gmail_oauth,
    create_gmail_authorization_url,
    decrypt_gmail_oauth_code_verifier,
)
from .models import Module, Role, RolePermission, Tenant, TenantMailgunSettings
from .serializers import (
    LoginSerializer,
    LogoutSerializer,
    ModuleSerializer,
    RefreshSerializer,
    RegisterSerializer,
    RolePermissionSerializer,
    RoleSerializer,
    TenantMailgunSettingsSerializer,
    UserInfoSerializer,
    UserManagementSerializer,
)

logger = logging.getLogger(__name__)


class IsSuperUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )


class SystemLogAdminListView(APIView):
    permission_classes = [IsSuperUser]

    def get(self, request):
        from campaigns.models import SystemLog

        queryset = SystemLog.objects.select_related("tenant").all()
        level = request.query_params.get("level")
        status_filter = request.query_params.get("status")
        search = request.query_params.get("search", "").strip()
        if level:
            queryset = queryset.filter(level=level.upper())
        if status_filter == "unread":
            queryset = queryset.filter(is_read=False)
        elif status_filter == "acknowledged":
            queryset = queryset.filter(is_acknowledged=True)
        if search:
            queryset = queryset.filter(models.Q(message__icontains=search) | models.Q(logger_name__icontains=search) | models.Q(module__icontains=search))
        queryset = queryset.order_by("-created_at")[:500]
        return Response({
            "results": [{
                "id": log.id,
                "tenant_id": log.tenant_id,
                "tenant_name": log.tenant.name if log.tenant else None,
                "level": log.level,
                "logger_name": log.logger_name,
                "module": log.module,
                "message": log.message,
                "source": log.source,
                "is_notification": log.is_notification,
                "is_read": log.is_read,
                "is_acknowledged": log.is_acknowledged,
                "created_at": log.created_at,
            } for log in queryset],
            "unread_notifications": SystemLog.objects.filter(is_notification=True, is_read=False).count(),
        })


class SystemLogAdminMarkAllReadView(APIView):
    permission_classes = [IsSuperUser]

    def post(self, request):
        from campaigns.models import SystemLog

        updated = SystemLog.objects.filter(is_read=False).update(is_read=True)
        return Response({"updated": updated})


class SystemLogAdminActionView(APIView):
    permission_classes = [IsSuperUser]

    def post(self, request, log_id):
        from campaigns.models import SystemLog
        log = get_object_or_404(SystemLog, pk=log_id)
        action = request.data.get("action")
        if action == "read":
            log.is_read = True
        elif action == "acknowledge":
            log.is_acknowledged = True
            log.is_read = True
        elif action == "dismiss":
            log.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response({"detail": "Invalid action."}, status=status.HTTP_400_BAD_REQUEST)
        log.save(update_fields=["is_read", "is_acknowledged"])
        return Response({"id": log.id, "is_read": log.is_read, "is_acknowledged": log.is_acknowledged})


class TenantMailgunSettingsListView(APIView):
    permission_classes = [IsSuperUser]

    def get(self, request):
        tenants = Tenant.objects.select_related("mailgun_settings").order_by("name", "id")
        return Response([
            {
                "id": tenant.id,
                "name": tenant.name,
                "configured": bool(
                    hasattr(tenant, "mailgun_settings")
                    and tenant.mailgun_settings.encrypted_api_key
                    and tenant.mailgun_settings.encrypted_webhook_signing_key
                ),
            }
            for tenant in tenants
        ])


class TenantAdminListView(APIView):
    permission_classes = [IsSuperUser]

    def get(self, request):
        tenants = Tenant.objects.select_related("mailgun_settings").prefetch_related("users").order_by("name", "id")
        return Response([
            {
                "id": tenant.id,
                "name": tenant.name,
                "created_at": tenant.created_at,
                "users_count": tenant.users.count(),
                "mailgun_configured": bool(
                    hasattr(tenant, "mailgun_settings")
                    and tenant.mailgun_settings.encrypted_api_key
                    and tenant.mailgun_settings.encrypted_webhook_signing_key
                    and tenant.mailgun_settings.sender_domain
                ),
                "has_api_key": bool(
                    hasattr(tenant, "mailgun_settings")
                    and tenant.mailgun_settings.encrypted_api_key
                ),
                "has_webhook_signing_key": bool(
                    hasattr(tenant, "mailgun_settings")
                    and tenant.mailgun_settings.encrypted_webhook_signing_key
                ),
                "sender_domain": getattr(
                    getattr(tenant, "mailgun_settings", None), "sender_domain", ""
                ),
            }
            for tenant in tenants
        ])


class TenantAdminDetailView(APIView):
    permission_classes = [IsSuperUser]

    def delete(self, request, tenant_id):
        tenant = get_object_or_404(Tenant, pk=tenant_id)
        if tenant.users.exists():
            return Response(
                {"detail": "Cannot delete a tenant that has users. Remove its users first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tenant.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OwnTenantMailgunSettingsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        tenant = request.user.tenant
        settings_instance = TenantMailgunSettings.objects.filter(tenant=tenant).first()
        if settings_instance is None:
            return Response({
                "tenant": tenant.id,
                "tenant_name": tenant.name,
                "default_from_email": "",
                "reply_to_email": "",
                "sender_domain": "",
                "has_api_key": False,
                "has_webhook_signing_key": False,
            })
        return Response(TenantMailgunSettingsSerializer(settings_instance).data)

    def put(self, request):
        tenant = request.user.tenant
        settings_instance = TenantMailgunSettings.objects.filter(tenant=tenant).first()
        serializer = TenantMailgunSettingsSerializer(
            settings_instance,
            data=request.data,
            partial=settings_instance is not None,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(tenant=tenant)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TenantMailgunSettingsDetailView(APIView):
    permission_classes = [IsSuperUser]

    def get(self, request, tenant_id):
        tenant = get_object_or_404(Tenant, pk=tenant_id)
        settings_instance = TenantMailgunSettings.objects.filter(tenant=tenant).first()
        if settings_instance is None:
            return Response({
                "tenant": tenant.id,
                "tenant_name": tenant.name,
                "default_from_email": "",
                "reply_to_email": "",
                "sender_domain": "",
                "has_api_key": False,
                "has_webhook_signing_key": False,
            })
        return Response(TenantMailgunSettingsSerializer(settings_instance).data)

    def put(self, request, tenant_id):
        tenant = get_object_or_404(Tenant, pk=tenant_id)
        settings_instance = TenantMailgunSettings.objects.filter(tenant=tenant).first()
        serializer = TenantMailgunSettingsSerializer(
            settings_instance,
            data=request.data,
            partial=settings_instance is not None,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(tenant=tenant)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserViewSet(viewsets.ModelViewSet):
    queryset = get_user_model().objects.all().order_by("id")
    serializer_class = UserManagementSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return self.queryset.filter(tenant_id=self.request.user.tenant_id)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)


class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.all().order_by("id")
    serializer_class = RoleSerializer
    permission_classes = [permissions.IsAdminUser]


class ModuleViewSet(viewsets.ModelViewSet):
    queryset = Module.objects.all().order_by("id")
    serializer_class = ModuleSerializer
    permission_classes = [permissions.IsAdminUser]


class RolePermissionViewSet(viewsets.ModelViewSet):
    queryset = RolePermission.objects.select_related("role", "module").all().order_by("id")
    serializer_class = RolePermissionSerializer
    permission_classes = [permissions.IsAdminUser]


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        logger.info(
            "event=auth.login.success actor_id=%s tenant_id=%s",
            user.pk,
            user.tenant_id or "none",
        )
        return Response({
            "access": serializer.validated_data["access"],
            "refresh": serializer.validated_data["refresh"],
            "user": UserInfoSerializer(serializer.validated_data["user"]).data,
        }, status=status.HTTP_200_OK)


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        logger.info(
            "event=auth.register.success actor_id=%s tenant_id=%s",
            user.pk,
            user.tenant_id or "none",
        )
        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserInfoSerializer(user).data,
        }, status=status.HTTP_201_CREATED)


class RefreshView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"detail": "Logout successful."}, status=status.HTTP_200_OK)


class CurrentUserView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserInfoSerializer(request.user).data, status=status.HTTP_200_OK)


class GoogleAuthorizationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        tenant_id = request.user.tenant_id
        if request.user.is_superuser:
            requested_tenant_id = request.query_params.get("tenant_id", tenant_id)
            tenant_id = Tenant.objects.filter(pk=requested_tenant_id).values_list(
                "pk", flat=True
            ).first()
            if tenant_id is None:
                return Response(
                    {"detail": "Select a valid tenant before connecting Gmail."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        try:
            state = secrets.token_urlsafe(32)
            authorization_url, code_verifier = create_gmail_authorization_url(state)
        except GmailOAuthConfigurationError as error:
            return Response(
                {"detail": str(error)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except GmailOAuthError as error:
            logger.exception("Could not start Gmail OAuth: %s", str(error))
            return Response(
                {"detail": "Google authorization could not be started."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        mailbox, _ = GmailMailbox.objects.get_or_create(
            tenant_id=tenant_id
        )
        mailbox.oauth_state_hash = hashlib.sha256(
            state.encode("utf-8")
        ).hexdigest()
        mailbox.oauth_state_created_at = timezone.now()
        mailbox.oauth_code_verifier = code_verifier
        mailbox.save(
            update_fields=[
                "oauth_state_hash",
                "oauth_state_created_at",
                "oauth_code_verifier",
                "updated_at",
            ]
        )
        return Response({"authorization_url": authorization_url})


class GoogleCallbackView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        state = request.query_params.get("state", "")
        code = request.query_params.get("code", "")
        if not state:
            return Response(
                {"detail": "OAuth state is missing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            expected_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
            mailbox = GmailMailbox.objects.select_for_update().filter(
                oauth_state_hash=expected_hash
            ).first()
            state_age = (
                timezone.now() - mailbox.oauth_state_created_at
                if mailbox and mailbox.oauth_state_created_at
                else None
            )
            valid_state = (
                mailbox is not None
                and mailbox.oauth_state_hash
                and state_age is not None
                and timedelta(0) <= state_age <= timedelta(minutes=10)
                and hmac.compare_digest(mailbox.oauth_state_hash, expected_hash)
            )
            if not valid_state:
                return Response(
                    {"detail": "OAuth state is invalid or expired. Start authorization again."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            encrypted_code_verifier = mailbox.oauth_code_verifier
            mailbox.oauth_state_hash = ""
            mailbox.oauth_state_created_at = None
            mailbox.oauth_code_verifier = ""
            mailbox.save(
                update_fields=[
                    "oauth_state_hash",
                    "oauth_state_created_at",
                    "oauth_code_verifier",
                    "updated_at",
                ]
            )

        provider_error = request.query_params.get("error")
        if provider_error:
            return Response(
                {"detail": "Google authorization was not completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not code:
            return Response(
                {"detail": "OAuth authorization code is missing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            code_verifier = decrypt_gmail_oauth_code_verifier(
                encrypted_code_verifier
            )
            connected_mailbox = complete_gmail_oauth(
                code,
                code_verifier=code_verifier,
                mailbox=mailbox,
            )
        except GmailOAuthConfigurationError as error:
            return Response(
                {"detail": str(error)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except GmailOAuthError as error:
            logger.exception("Gmail OAuth callback failed: %s", str(error))
            return Response(
                {"detail": "Google authorization could not be completed. Please check the server logs."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        redirect_uri = settings.GMAIL_OAUTH_FRONTEND_REDIRECT_URI
        separator = "&" if "?" in redirect_uri else "?"
        return redirect(
            f"{redirect_uri}{separator}{urlencode({'gmail': 'connected'})}"
        )


class GmailConnectionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _tenant_id(self, request):
        if request.user.is_superuser:
            requested_tenant_id = request.query_params.get(
                "tenant_id", request.user.tenant_id
            )
            return Tenant.objects.filter(pk=requested_tenant_id).values_list(
                "pk", flat=True
            ).first()
        return request.user.tenant_id

    def get(self, request):
        tenant_id = self._tenant_id(request)
        if tenant_id is None:
            return Response(
                {"detail": "Select a valid tenant."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        mailbox = GmailMailbox.objects.filter(tenant_id=tenant_id).first()
        return Response(
            {
                "connected": bool(mailbox and mailbox.encrypted_credentials),
                "email": mailbox.email if mailbox and mailbox.encrypted_credentials else "",
                "last_sync_at": mailbox.last_sync_at if mailbox else None,
            }
        )

    def delete(self, request):
        tenant_id = self._tenant_id(request)
        if tenant_id is None:
            return Response(
                {"detail": "Select a valid tenant."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        mailbox = GmailMailbox.objects.filter(tenant_id=tenant_id).first()
        if mailbox:
            mailbox.email = ""
            mailbox.encrypted_credentials = ""
            mailbox.history_id = ""
            mailbox.last_sync_at = None
            mailbox.oauth_state_hash = ""
            mailbox.oauth_state_created_at = None
            mailbox.oauth_code_verifier = ""
            mailbox.save(
                update_fields=[
                    "email",
                    "encrypted_credentials",
                    "history_id",
                    "last_sync_at",
                    "oauth_state_hash",
                    "oauth_state_created_at",
                    "oauth_code_verifier",
                    "updated_at",
                ]
            )
        return Response({"connected": False, "email": ""})
