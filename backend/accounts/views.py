from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenRefreshView, TokenViewBase

from audit.services import Action, diff, record

from .models import BusinessSettings, Role, UserRole
from .rbac import SETTINGS_MANAGE, SETTINGS_VIEW, STAFF_MANAGE
from .serializers import (
    AuthPayloadSerializer,
    BusinessSerializer,
    BusinessSettingsSerializer,
    ChangePasswordSerializer,
    DetailSerializer,
    LoginSerializer,
    LogoutSerializer,
    MeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    RoleSerializer,
    StaffCreateSerializer,
    StaffPasswordResetSerializer,
    StaffSerializer,
    StaffUpdateSerializer,
    TenantTokenRefreshSerializer,
    UserSerializer,
    auth_payload,
)
from .services import (
    add_staff,
    assignable_role_ids,
    change_own_password,
    change_staff,
    get_permission_codenames,
    reset_staff_password,
)

PASSWORD_RESET_SENT = _("If an account exists for this email, a reset link has been sent.")

VALIDATION_ERROR = OpenApiResponse(description="Validation error.")
THROTTLED = OpenApiResponse(description="Too many requests from this IP.")


class RegisterView(generics.GenericAPIView):
    """FR-1: create an owner account with its business, then log it in."""

    serializer_class = RegisterSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "register"

    @extend_schema(
        tags=["auth"],
        summary="Register an owner and their business",
        auth=[],
        responses={201: AuthPayloadSerializer, 400: VALIDATION_ERROR, 429: THROTTLED},
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, business = serializer.save()
        return Response(auth_payload(user, business, Role.OWNER), status=status.HTTP_201_CREATED)


class LoginView(TokenViewBase):
    serializer_class = LoginSerializer
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "login"

    @extend_schema(
        tags=["auth"],
        summary="Log in to a business",
        description=(
            "`business_id` is only needed when the account belongs to several "
            "businesses; the 400 response then lists them under `businesses`."
        ),
        auth=[],
        responses={
            200: AuthPayloadSerializer,
            400: OpenApiResponse(
                description="Several businesses and none chosen, or not a member of `business_id`."
            ),
            401: OpenApiResponse(description="Invalid credentials or no active membership."),
            429: THROTTLED,
        },
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class RefreshView(TokenRefreshView):
    serializer_class = TenantTokenRefreshSerializer
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "token_refresh"

    @extend_schema(
        tags=["auth"],
        summary="Rotate a refresh token",
        description="Returns a new access/refresh pair; the submitted refresh token stops working.",
        auth=[],
        responses={
            200: TenantTokenRefreshSerializer,
            401: OpenApiResponse(description="Refresh token invalid, revoked, or membership inactive."),
            429: THROTTLED,
        },
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class LogoutView(generics.GenericAPIView):
    serializer_class = LogoutSerializer
    required_permissions = ()
    allow_pending_password_change = True

    @extend_schema(
        tags=["auth"],
        summary="Log out (blacklist a refresh token)",
        responses={204: None, 400: VALIDATION_ERROR},
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(generics.GenericAPIView):
    serializer_class = MeSerializer
    required_permissions = ()
    allow_pending_password_change = True

    @extend_schema(tags=["auth"], summary="Current user, business, role and permissions")
    def get(self, request):
        return Response(
            {
                "user": UserSerializer(request.user).data,
                "business": BusinessSerializer(request.business).data,
                "role": request.membership.role.name,
                "permissions": sorted(get_permission_codenames(request.membership)),
            }
        )


class PasswordResetRequestView(generics.GenericAPIView):
    """FR-4: always answers 202 with the same body, so the response never
    reveals whether the account exists."""

    serializer_class = PasswordResetRequestSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "password_reset"

    @extend_schema(
        tags=["password reset"],
        summary="Email a password reset link",
        auth=[],
        responses={202: DetailSerializer, 400: VALIDATION_ERROR, 429: THROTTLED},
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": PASSWORD_RESET_SENT}, status=status.HTTP_202_ACCEPTED)


class PasswordResetConfirmView(generics.GenericAPIView):
    """FR-4: set a new password with a single-use token. Ends all sessions."""

    serializer_class = PasswordResetConfirmSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "password_reset"

    @extend_schema(
        tags=["password reset"],
        summary="Set a new password with a reset token",
        auth=[],
        responses={
            204: None,
            400: OpenApiResponse(
                description="`token` invalid, used or expired, or `new_password` too weak."
            ),
            429: THROTTLED,
        },
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


FORBIDDEN = OpenApiResponse(description="Your role lacks the required permission.")


@extend_schema_view(
    get=extend_schema(
        tags=["settings"],
        summary="Get business settings",
        responses={200: BusinessSettingsSerializer, 403: FORBIDDEN},
    ),
    patch=extend_schema(
        tags=["settings"],
        summary="Update business settings",
        responses={200: BusinessSettingsSerializer, 400: VALIDATION_ERROR, 403: FORBIDDEN},
    ),
)
class BusinessSettingsView(generics.RetrieveUpdateAPIView):
    """The active business's settings. The row is found through the
    tenant-scoped manager, so there is no id in the URL to tamper with."""

    serializer_class = BusinessSettingsSerializer
    http_method_names = ["get", "patch", "head", "options"]
    required_permissions = {"GET": (SETTINGS_VIEW,), "PATCH": (SETTINGS_MANAGE,)}

    def get_object(self):
        return BusinessSettings.objects.get()

    @transaction.atomic
    def perform_update(self, serializer):
        changes = diff(serializer.instance, serializer.validated_data)
        serializer.save()
        if changes:
            record(Action.SETTINGS_CHANGE, target=serializer.instance, label="", changes=changes)


def _service_call(fn, **kwargs):
    """Run an accounts service; its domain ValidationErrors become 400s."""
    try:
        return fn(**kwargs)
    except DjangoValidationError as exc:
        if hasattr(exc, "error_dict"):
            raise ValidationError(exc.message_dict)
        raise ValidationError({"non_field_errors": exc.messages})


class ChangePasswordView(generics.GenericAPIView):
    """Choose a new password, including the first one after a temporary
    password. Ends the user's other sessions and returns fresh tokens."""

    serializer_class = ChangePasswordSerializer
    required_permissions = ()
    allow_pending_password_change = True
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "login"

    @extend_schema(
        tags=["auth"],
        summary="Change my password",
        responses={
            200: AuthPayloadSerializer,
            400: OpenApiResponse(description="Current password wrong, or new password too weak."),
            429: THROTTLED,
        },
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _service_call(change_own_password, user=request.user, **serializer.validated_data)
        return Response(auth_payload(request.user, request.business, request.membership.role.name))


class StaffContextMixin:
    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):
            context["assignable_role_ids"] = assignable_role_ids(self.request.membership)
        return context


@extend_schema_view(
    list=extend_schema(tags=["staff"], summary="List staff", responses={200: StaffSerializer(many=True), 403: FORBIDDEN}),
    retrieve=extend_schema(tags=["staff"], summary="Get a staff member", responses={200: StaffSerializer, 403: FORBIDDEN}),
    create=extend_schema(
        tags=["staff"],
        summary="Add a staff member",
        description=(
            "Creates an account with `temp_password`, which they must change at first "
            "login. An email that already has an account is refused. You can only give "
            "a role with fewer powers than your own (never Owner)."
        ),
        request=StaffCreateSerializer,
        responses={201: StaffSerializer, 400: VALIDATION_ERROR, 403: FORBIDDEN},
    ),
    partial_update=extend_schema(
        tags=["staff"],
        summary="Change a staff member's role, name or phone, or turn their access off/on",
        description=(
            "Not for yourself or the Owner. Turning access off works from their next request. "
            "Name and phone can't be changed for an account also used at another business."
        ),
        request=StaffUpdateSerializer,
        responses={200: StaffSerializer, 400: VALIDATION_ERROR, 403: FORBIDDEN},
    ),
    reset_password=extend_schema(
        tags=["staff"],
        summary="Give a staff member a new temporary password",
        description=(
            "Logs them out everywhere; they choose their own password at next login. "
            "Refused for an account that is also used at another business."
        ),
        request=StaffPasswordResetSerializer,
        responses={204: None, 400: VALIDATION_ERROR, 403: FORBIDDEN},
    ),
)
class StaffViewSet(
    StaffContextMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """People with access to the active business. Ids are membership ids, so
    another business's staff are a 404. Nobody is deleted (their sales point
    at them); turn access off instead."""

    serializer_class = StaffSerializer
    required_permissions = (STAFF_MANAGE,)
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ("is_active", "role")
    search_fields = ("user__email", "user__first_name", "user__last_name", "user__phone")
    ordering_fields = ("user__first_name", "user__email", "created_at")
    ordering = ("user__first_name", "user__email")

    def get_queryset(self):
        return UserRole.objects.select_related("user", "role")

    def create(self, request, *args, **kwargs):
        serializer = StaffCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        membership = _service_call(add_staff, actor=request.membership, **serializer.validated_data)
        return Response(self.get_serializer(membership).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        membership = self.get_object()
        serializer = StaffUpdateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        membership = _service_call(
            change_staff, membership=membership, actor=request.membership, **serializer.validated_data
        )
        return Response(self.get_serializer(membership).data)

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        membership = self.get_object()
        serializer = StaffPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _service_call(
            reset_staff_password, membership=membership, actor=request.membership, **serializer.validated_data
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["staff"], summary="List roles, and which ones you may give", responses={200: RoleSerializer(many=True), 403: FORBIDDEN})
class RoleListView(StaffContextMixin, generics.ListAPIView):
    serializer_class = RoleSerializer
    required_permissions = (STAFF_MANAGE,)
    pagination_class = None

    def get_queryset(self):
        return Role.objects.prefetch_related("grants__permission").order_by("name")
