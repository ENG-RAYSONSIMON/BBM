from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
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

from .models import Business, BusinessSettings, Role, User, UserRole
from .services import (
    InvalidResetToken,
    confirm_password_reset,
    get_active_membership,
    get_active_memberships,
    register_owner,
    request_password_reset,
)
from .tokens import tokens_for

INVALID_CREDENTIALS = _("No active account found with the given credentials.")
DUPLICATE_EMAIL = _("A user with this email already exists.")
NO_ACTIVE_MEMBERSHIP = _("No active business membership for this token.")
INVALID_RESET_TOKEN = _("Reset link is invalid or expired.")


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "phone", "must_change_password")
        read_only_fields = fields


class BusinessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        fields = ("id", "name", "tin", "phone", "email", "address", "currency")
        read_only_fields = fields


class AuthPayloadSerializer(serializers.Serializer):
    """Response of register and login (documentation only)."""

    refresh = serializers.CharField()
    access = serializers.CharField()
    user = UserSerializer()
    business = BusinessSerializer()
    role = serializers.CharField()


class MeSerializer(serializers.Serializer):
    """Response of /auth/me/ (documentation only)."""

    user = UserSerializer()
    business = BusinessSerializer()
    role = serializers.CharField()
    permissions = serializers.ListField(child=serializers.CharField())


class DetailSerializer(serializers.Serializer):
    detail = serializers.CharField()


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

        update_last_login(None, user)
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


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)

    def save(self, **kwargs):
        request_password_reset(self.validated_data["email"])


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128, trim_whitespace=True)
    new_password = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )

    def save(self, **kwargs):
        try:
            return confirm_password_reset(
                self.validated_data["token"], self.validated_data["new_password"]
            )
        except InvalidResetToken:
            raise serializers.ValidationError({"token": [INVALID_RESET_TOKEN]})
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})


class BusinessSettingsSerializer(serializers.ModelSerializer):
    tax_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100
    )

    class Meta:
        model = BusinessSettings
        fields = ("low_stock_threshold", "expiry_warning_days", "tax_rate", "loyalty_enabled")


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"},
        help_text="The temporary password, on first login.",
    )
    new_password = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )


# Staff management (UserRole rows of the active business)

class StaffSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    last_login = serializers.DateTimeField(source="user.last_login", read_only=True, allow_null=True)
    role_name = serializers.CharField(source="role.name", read_only=True)
    must_change_password = serializers.BooleanField(
        source="user.must_change_password", read_only=True,
        help_text="Still on a temporary password.",
    )
    is_you = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField(
        help_text="Whether the caller may change this person's role, access or password."
    )

    class Meta:
        model = UserRole
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "role_name",
            "is_active",
            "must_change_password",
            "last_login",
            "is_you",
            "can_manage",
            "created_at",
        )
        read_only_fields = fields

    def get_is_you(self, membership) -> bool:
        return membership.user_id == self.context["request"].user.pk

    def get_can_manage(self, membership) -> bool:
        return not self.get_is_you(membership) and membership.role_id in self.context["assignable_role_ids"]


def _role_field(**kwargs):
    # Scoped manager: another business's role is "does not exist".
    return serializers.PrimaryKeyRelatedField(queryset=Role.objects.all(), **kwargs)


def _temp_password_field(**kwargs):
    return serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}, **kwargs
    )


class StaffCreateSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    first_name = serializers.CharField(max_length=150, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=150, allow_blank=True, default="")
    phone = serializers.CharField(max_length=20, allow_blank=True, default="")
    role = _role_field()
    temp_password = _temp_password_field(help_text="They must change it at first login.")


class StaffUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150, allow_blank=True, required=False)
    last_name = serializers.CharField(max_length=150, allow_blank=True, required=False)
    phone = serializers.CharField(max_length=20, allow_blank=True, required=False)
    role = _role_field(required=False)
    is_active = serializers.BooleanField(required=False, help_text="False turns their access off.")


class StaffPasswordResetSerializer(serializers.Serializer):
    temp_password = _temp_password_field()


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    assignable = serializers.SerializerMethodField(help_text="Whether the caller may give this role.")

    class Meta:
        model = Role
        fields = ("id", "name", "is_system", "permissions", "assignable")
        read_only_fields = fields

    def get_permissions(self, role) -> list[str]:
        return sorted(grant.permission.codename for grant in role.grants.all())

    def get_assignable(self, role) -> bool:
        return role.pk in self.context["assignable_role_ids"]
