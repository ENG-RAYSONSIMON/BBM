from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView, TokenViewBase

from .models import Role
from .serializers import (
    BusinessSerializer,
    LoginSerializer,
    LogoutSerializer,
    RegisterSerializer,
    TenantTokenRefreshSerializer,
    UserSerializer,
    auth_payload,
)


class RegisterView(generics.GenericAPIView):
    """FR-1: create an owner account with its business, then log it in."""

    serializer_class = RegisterSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, business = serializer.save()
        return Response(auth_payload(user, business, Role.OWNER), status=status.HTTP_201_CREATED)


class LoginView(TokenViewBase):
    serializer_class = LoginSerializer


class RefreshView(TokenRefreshView):
    serializer_class = TenantTokenRefreshSerializer


class LogoutView(generics.GenericAPIView):
    serializer_class = LogoutSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response(
            {
                "user": UserSerializer(request.user).data,
                "business": BusinessSerializer(request.business).data,
                "role": request.membership.role.name,
            }
        )
