import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
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
)
from .models import Module, Role, RolePermission
from .serializers import (
    LoginSerializer,
    LogoutSerializer,
    ModuleSerializer,
    RefreshSerializer,
    RegisterSerializer,
    RolePermissionSerializer,
    RoleSerializer,
    UserInfoSerializer,
    UserManagementSerializer,
)

logger = logging.getLogger(__name__)


class UserViewSet(viewsets.ModelViewSet):
    queryset = get_user_model().objects.all().order_by("id")
    serializer_class = UserManagementSerializer
    permission_classes = [permissions.IsAdminUser]


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
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        try:
            state = secrets.token_urlsafe(32)
            authorization_url = create_gmail_authorization_url(state)
        except GmailOAuthConfigurationError as error:
            return Response(
                {"detail": str(error)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        mailbox, _ = GmailMailbox.objects.get_or_create(pk=1)
        mailbox.oauth_state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
        mailbox.oauth_state_created_at = timezone.now()
        mailbox.save(update_fields=["oauth_state_hash", "oauth_state_created_at", "updated_at"])
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
            mailbox = GmailMailbox.objects.select_for_update().filter(pk=1).first()
            expected_hash = (
                hashlib.sha256(state.encode("utf-8")).hexdigest() if mailbox else ""
            )
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
            mailbox.oauth_state_hash = ""
            mailbox.oauth_state_created_at = None
            mailbox.save(
                update_fields=["oauth_state_hash", "oauth_state_created_at", "updated_at"]
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
            connected_mailbox = complete_gmail_oauth(code)
        except GmailOAuthConfigurationError as error:
            return Response(
                {"detail": str(error)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except GmailOAuthError as error:
          logger.exception(
              "Gmail OAuth callback failed: %s",
              str(error),
          )
          return Response(
              {"detail": "Google authorization could not be completed. Please check the server logs."},
              status=status.HTTP_502_BAD_GATEWAY,
          )

        return Response(
            {"status": "connected", "mailbox": connected_mailbox.email},
            status=status.HTTP_200_OK,
        )
