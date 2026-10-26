from email.utils import parseaddr

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenBlacklistSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .mailgun_secrets import encrypt_mailgun_secret
from .models import Module, Role, RolePermission, Tenant, TenantMailgunSettings


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ("id", "name", "code")


class ModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = ("id", "name", "code")


class UserInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ("id", "username", "email", "first_name", "last_name", "is_superuser")
        read_only_fields = fields


class TenantMailgunSettingsSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    has_api_key = serializers.SerializerMethodField()
    has_webhook_signing_key = serializers.SerializerMethodField()
    default_from_email = serializers.CharField(max_length=320)
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=False)
    webhook_signing_key = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=False,
    )

    class Meta:
        model = TenantMailgunSettings
        fields = (
            "tenant",
            "tenant_name",
            "default_from_email",
            "sender_domain",
            "api_key",
            "webhook_signing_key",
            "has_api_key",
            "has_webhook_signing_key",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "tenant",
            "tenant_name",
            "has_api_key",
            "has_webhook_signing_key",
            "created_at",
            "updated_at",
        )

    def get_has_api_key(self, instance):
        return bool(instance.encrypted_api_key)

    def get_has_webhook_signing_key(self, instance):
        return bool(instance.encrypted_webhook_signing_key)

    def validate_default_from_email(self, value):
        if "\r" in value or "\n" in value:
            raise serializers.ValidationError("Line breaks are not allowed.")
        _, email_address = parseaddr(value)
        try:
            validate_email(email_address)
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                "Enter an email address, optionally with a display name."
            ) from error
        return value

    def validate_sender_domain(self, value):
        try:
            validate_email(f"mailgun@{value}")
        except DjangoValidationError as error:
            raise serializers.ValidationError("Enter a valid Mailgun sender domain.") from error
        return value

    def validate(self, attrs):
        if self.instance is None:
            missing = [
                field
                for field in ("api_key", "webhook_signing_key")
                if not attrs.get(field)
            ]
            if missing:
                raise serializers.ValidationError({
                    field: "This field is required when creating Mailgun settings."
                    for field in missing
                })
        return attrs

    def create(self, validated_data):
        api_key = validated_data.pop("api_key")
        webhook_signing_key = validated_data.pop("webhook_signing_key")
        return TenantMailgunSettings.objects.create(
            **validated_data,
            encrypted_api_key=encrypt_mailgun_secret(api_key),
            encrypted_webhook_signing_key=encrypt_mailgun_secret(webhook_signing_key),
        )

    def update(self, instance, validated_data):
        api_key = validated_data.pop("api_key", None)
        webhook_signing_key = validated_data.pop("webhook_signing_key", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if api_key is not None:
            instance.encrypted_api_key = encrypt_mailgun_secret(api_key)
        if webhook_signing_key is not None:
            instance.encrypted_webhook_signing_key = encrypt_mailgun_secret(
                webhook_signing_key
            )
        instance.save()
        return instance


class UserManagementSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=False,
        trim_whitespace=False,
    )

    class Meta:
        model = get_user_model()
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_active",
            "password",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        password = attrs.get("password")
        if password is None:
            if self.instance is None:
                raise serializers.ValidationError(
                    {"password": "This field is required."}
                )
            return attrs

        user = self.instance or get_user_model()()
        for field in ("username", "email", "first_name", "last_name"):
            if field in attrs:
                setattr(user, field, attrs[field])

        try:
            validate_password(password, user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                {"password": exc.messages}
            ) from exc

        return attrs

    def create(self, validated_data):
        return get_user_model().objects.create_user(**validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password is not None:
            instance.set_password(password)
        instance.save()
        return instance


class RolePermissionSerializer(serializers.ModelSerializer):
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all())
    module = serializers.PrimaryKeyRelatedField(queryset=Module.objects.all())
    role_name = serializers.CharField(source="role.name", read_only=True)
    module_name = serializers.CharField(source="module.name", read_only=True)

    class Meta:
        model = RolePermission
        fields = (
            "id",
            "role",
            "role_name",
            "module",
            "module_name",
            "can_view",
            "can_create",
            "can_edit",
            "can_delete",
        )

    def validate(self, attrs):
        role = attrs.get("role")
        module = attrs.get("module")
        if role is None or module is None:
            return attrs

        if RolePermission.objects.filter(role=role, module=module).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError({"non_field_errors": ["This role already has permissions for this module."]})
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user_model = get_user_model()
        user = user_model.objects.filter(email__iexact=attrs["email"]).order_by("pk").first()
        if user is None or not user.is_active:
            raise AuthenticationFailed("Invalid email or password.")

        authenticated_user = authenticate(
            request=self.context.get("request"),
            username=user.get_username(),
            password=attrs["password"],
        )
        if authenticated_user is None or not authenticated_user.is_active:
            raise AuthenticationFailed("Invalid email or password.")

        refresh = RefreshToken.for_user(authenticated_user)
        return {
            "user": authenticated_user,
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }


class RegisterSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value):
        if get_user_model().objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        user_model = get_user_model()
        validate_password(attrs["password"], user=user_model(
            username=attrs["email"],
            email=attrs["email"],
            first_name=attrs["first_name"],
            last_name=attrs["last_name"],
        ))
        return attrs

    def create(self, validated_data):
        user_model = get_user_model()
        email = validated_data["email"]
        role, _ = Role.objects.get_or_create(
            code="admin",
            defaults={"name": "Admin"},
        )
        tenant_name = " ".join(
            part
            for part in (
                validated_data["first_name"],
                validated_data["last_name"],
            )
            if part
        )
        validated_data["tenant"] = Tenant.objects.create(
            name=tenant_name or email
        )
        return user_model.objects.create_user(
            username=email,
            email=email,
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            tenant=validated_data["tenant"],
            role=role,
            password=validated_data["password"],
        )


class RefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        try:
            return super().validate(attrs)
        except TokenError as exc:
            raise InvalidToken(str(exc)) from exc


class LogoutSerializer(TokenBlacklistSerializer):
    def validate(self, attrs):
        try:
            return super().validate(attrs)
        except TokenError as exc:
            raise InvalidToken(str(exc)) from exc
