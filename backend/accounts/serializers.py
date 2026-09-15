from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from core.tenancy import TENANT_CLAIM

from .models import Business, User
from .services import get_active_membership, get_active_memberships, register_owner
from .tokens import tokens_for

INVALID_CREDENTIALS = _("No active account found with the given credentials.")
DUPLICATE_EMAIL = _("A user with this email already exists.")
NO_ACTIVE_MEMBERSHIP = _("No active business membership for this token.")


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "phone")
        read_only_fields = fields


class BusinessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        fields = ("id", "name", "tin", "phone", "email", "address", "currency")
        read_only_fields = fields


def auth_payload(user, business, role_name):
    return {
        **tokens_for(user, business),
        "user": UserSerializer(user).data,
        "business": BusinessSerializer(business).data,
        "role": role_name,
    }


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )
    first_name = serializers.CharField(max_length=150, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=150, allow_blank=True, default="")
    phone = serializers.CharField(max_length=20, allow_blank=True, default="")
    business_name = serializers.CharField(max_length=255)

    def validate_email(self, value):
        email = User.objects.normalize_email(value)
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(DUPLICATE_EMAIL)
        return email

    def validate(self, attrs):
        candidate = User(
            email=attrs["email"], first_name=attrs["first_name"], last_name=attrs["last_name"]
        )
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, validated_data):
        try:
            return register_owner(**validated_data)
        except IntegrityError:
            # Lost a race with a concurrent registration for the same email.
            raise serializers.ValidationError({"email": [DUPLICATE_EMAIL]})


class LoginSerializer(serializers.Serializer):
    """FR-2 login. `business_id` only selects among the user's own verified
    memberships; it is required only when there is more than one."""

    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )
    business_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"),
            email=attrs["email"],
            password=attrs["password"],
        )
        if user is None:
            raise AuthenticationFailed(INVALID_CREDENTIALS, code="no_active_account")

        memberships = get_active_memberships(user)
        if not memberships:
            raise AuthenticationFailed(INVALID_CREDENTIALS, code="no_active_account")

        requested = attrs.get("business_id")
        if requested is not None:
            membership = next((m for m in memberships if m.business_id == requested), None)
            if membership is None:
                raise serializers.ValidationError(
                    {"business_id": [_("You are not a member of this business.")]}
                )
        elif len(memberships) == 1:
            membership = memberships[0]
        else:
            raise serializers.ValidationError(
                {
                    "business_id": [_("This account belongs to several businesses; choose one.")],
                    "businesses": [
                        {"id": str(m.business_id), "name": m.business.name} for m in memberships
                    ],
                }
            )

        return auth_payload(user, membership.business, membership.role.name)


class TenantTokenRefreshSerializer(TokenRefreshSerializer):
    """FR-2 rotating refresh that also refuses tokens whose business
    membership is no longer active."""

    def validate(self, attrs):
        refresh = self.token_class(attrs["refresh"])
        membership = get_active_membership(
            refresh.payload.get(api_settings.USER_ID_CLAIM),
            refresh.payload.get(TENANT_CLAIM),
        )
        if membership is None:
            raise AuthenticationFailed(NO_ACTIVE_MEMBERSHIP, code="no_active_membership")
        return super().validate(attrs)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def validate_refresh(self, value):
        try:
            token = RefreshToken(value)
        except TokenError:
            raise serializers.ValidationError(_("Token is invalid or expired."))
        if str(token.get(api_settings.USER_ID_CLAIM)) != str(self.context["request"].user.pk):
            raise serializers.ValidationError(_("Token is invalid or expired."))
        self._token = token
        return value

    def save(self, **kwargs):
        self._token.blacklist()
