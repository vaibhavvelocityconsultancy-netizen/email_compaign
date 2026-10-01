from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenBlacklistSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken


class UserInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ("id", "username", "email", "first_name", "last_name")
        read_only_fields = fields


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

