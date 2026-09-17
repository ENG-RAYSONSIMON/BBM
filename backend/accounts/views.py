from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenRefreshView, TokenViewBase

from .models import BusinessSettings, Role
from .rbac import SETTINGS_MANAGE, SETTINGS_VIEW
from .serializers import (
    AuthPayloadSerializer,
    BusinessSerializer,
    BusinessSettingsSerializer,
    DetailSerializer,
    LoginSerializer,
    LogoutSerializer,
    MeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    TenantTokenRefreshSerializer,
    UserSerializer,
    auth_payload,
)
from .services import get_permission_codenames

PASSWORD_RESET_SENT = "If an account exists for this email, a reset link has been sent."

VALIDATION_ERROR = OpenApiResponse(description="Validation error.")
THROTTLED = OpenApiResponse(description="Too many requests from this IP.")


class RegisterView(generics.GenericAPIView):
    """FR-1: create an owner account with its business, then log it in."""

    serializer_class = RegisterSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        tags=["auth"],
        summary="Register an owner and their business",
        auth=[],
        responses={201: AuthPayloadSerializer, 400: VALIDATION_ERROR},
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, business = serializer.save()
        return Response(auth_payload(user, business, Role.OWNER), status=status.HTTP_201_CREATED)


class LoginView(TokenViewBase):
    serializer_class = LoginSerializer

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
        },
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class RefreshView(TokenRefreshView):
    serializer_class = TenantTokenRefreshSerializer

    @extend_schema(
        tags=["auth"],
        summary="Rotate a refresh token",
        description="Returns a new access/refresh pair; the submitted refresh token stops working.",
        auth=[],
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class LogoutView(generics.GenericAPIView):
    serializer_class = LogoutSerializer
    required_permissions = ()

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
