import re

import django_filters
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, mixins, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.rbac import PURCHASES_MANAGE, PURCHASES_VIEW

from .models import Purchase
from .serializers import (
    CancelSerializer,
    PurchaseDetailSerializer,
    PurchaseSerializer,
    PurchaseWriteSerializer,
)
from .services import cancel_purchase, receive_purchase, save_draft

PURCHASE_PERMISSIONS = {
    "GET": (PURCHASES_VIEW,),
    "POST": (PURCHASES_MANAGE,),
    "PUT": (PURCHASES_MANAGE,),
}


def _service_call(fn, **kwargs):
    """Run a purchases service; its domain ValidationErrors become 400s.
    Errors not tied to a field are sent as non_field_errors."""
    try:
        return fn(**kwargs)
    except DjangoValidationError as exc:
        if hasattr(exc, "error_dict"):
            raise ValidationError(exc.message_dict)
        raise ValidationError({"non_field_errors": exc.messages})


def _purchase_queryset():
    return Purchase.objects.select_related("supplier", "created_by").annotate(item_count=Count("items"))


def _purchase_detail(pk, context):
    purchase = (
        _purchase_queryset()
        .select_related("received_by", "cancelled_by")
        .prefetch_related("items__product")
        .get(pk=pk)
    )
    return PurchaseDetailSerializer(purchase, context=context).data


class PurchaseFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="purchase_date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="purchase_date", lookup_expr="lte")
    number = django_filters.CharFilter(method="filter_number", label="Purchase number, e.g. P-000012 or 12.")

    class Meta:
        model = Purchase
        fields = ("status", "supplier")

    def filter_number(self, queryset, name, value):
        digits = re.sub(r"\D", "", value)
        return queryset.filter(number=int(digits)) if digits else queryset.none()


@extend_schema_view(
    list=extend_schema(tags=["purchases"], summary="List purchases"),
    retrieve=extend_schema(tags=["purchases"], summary="Get a purchase with its lines"),
    create=extend_schema(
        tags=["purchases"],
        summary="Create a draft purchase",
        description="A draft holds no stock. Receive it to put the stock on the shelf.",
        request=PurchaseWriteSerializer,
        responses={201: PurchaseDetailSerializer},
    ),
    update=extend_schema(
        tags=["purchases"],
        summary="Replace a draft purchase's details and lines",
        request=PurchaseWriteSerializer,
        responses={200: PurchaseDetailSerializer},
    ),
)
class PurchaseViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """FR-14 purchases. Only drafts change; nothing is deleted."""

    required_permissions = PURCHASE_PERMISSIONS
    http_method_names = ["get", "post", "put", "head", "options"]
    filterset_class = PurchaseFilter
    search_fields = ("reference", "supplier__name", "note")
    ordering_fields = ("created_at", "purchase_date", "number", "total")
    ordering = ("-created_at",)

    def get_queryset(self):
        return _purchase_queryset()

    def get_serializer_class(self):
        if self.action in ("create", "update"):
            return PurchaseWriteSerializer
        if self.action == "retrieve":
            return PurchaseDetailSerializer
        return PurchaseSerializer

    def retrieve(self, request, *args, **kwargs):
        purchase = self.get_object()
        return Response(_purchase_detail(purchase.pk, self.get_serializer_context()))

    def _save(self, request, purchase=None):
        serializer = PurchaseWriteSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return _service_call(
            save_draft,
            user=request.user,
            purchase=purchase,
            lines=data["items"],
            supplier=data["supplier"],
            reference=data["reference"],
            purchase_date=data["purchase_date"],
            note=data["note"],
        )

    def create(self, request, *args, **kwargs):
        purchase = self._save(request)
        return Response(
            _purchase_detail(purchase.pk, self.get_serializer_context()), status=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        purchase = self._save(request, purchase=self.get_object())
        return Response(_purchase_detail(purchase.pk, self.get_serializer_context()))


class PurchaseActionView(generics.GenericAPIView):
    """Base for POST actions on one purchase; another business's purchase is a 404."""

    required_permissions = (PURCHASES_MANAGE,)

    def get_queryset(self):
        return Purchase.objects.all()

    def get_purchase(self):
        return get_object_or_404(self.get_queryset(), pk=self.kwargs["pk"])


@extend_schema(
    tags=["purchases"],
    summary="Receive a draft purchase",
    description=(
        "One atomic transaction: creates or reuses each line's batch, writes a "
        "PURCHASE stock movement per line and sets each product's cost price to "
        "the cost just paid."
    ),
    request=None,
    responses={200: PurchaseDetailSerializer},
)
class PurchaseReceiveView(PurchaseActionView):
    serializer_class = PurchaseDetailSerializer

    def post(self, request, pk):
        purchase = self.get_purchase()
        _service_call(receive_purchase, purchase=purchase, user=request.user)
        return Response(_purchase_detail(purchase.pk, self.get_serializer_context()))


@extend_schema(
    tags=["purchases"],
    summary="Cancel a draft purchase",
    request=CancelSerializer,
    responses={200: PurchaseDetailSerializer},
)
class PurchaseCancelView(PurchaseActionView):
    serializer_class = CancelSerializer

    def post(self, request, pk):
        purchase = self.get_purchase()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _service_call(cancel_purchase, purchase=purchase, user=request.user, **serializer.validated_data)
        return Response(_purchase_detail(purchase.pk, self.get_serializer_context()))
