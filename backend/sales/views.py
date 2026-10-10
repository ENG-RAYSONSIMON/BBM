import re

import django_filters
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics, mixins, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.models import User, UserRole
from accounts.rbac import SALES_CREATE, SALES_VIEW, SALES_VOID
from core.views import TenantModelViewSet

from .models import Customer, Sale
from .serializers import (
    CustomerSerializer,
    PaymentCreateSerializer,
    PaymentSerializer,
    SaleCreateSerializer,
    SaleDetailSerializer,
    SaleSerializer,
    SalesSummarySerializer,
    VoidSerializer,
)
from .services import (
    create_sale,
    record_payment,
    sales_summary,
    void_sale,
    with_customer_balance,
    with_payment_totals,
)

SALES_PERMISSIONS = {"GET": (SALES_VIEW,), "POST": (SALES_CREATE,)}
CUSTOMER_PERMISSIONS = {
    "GET": (SALES_VIEW,),
    "POST": (SALES_CREATE,),
    "PATCH": (SALES_CREATE,),
    # Deleting is destructive, so it sits with the Owner-only sales permission.
    "DELETE": (SALES_VOID,),
}


def _service_call(fn, **kwargs):
    """Run a sales service; its domain ValidationErrors become 400s. Errors
    not tied to a field are sent as non_field_errors."""
    try:
        return fn(**kwargs)
    except DjangoValidationError as exc:
        if hasattr(exc, "error_dict"):
            raise ValidationError(exc.message_dict)
        raise ValidationError({"non_field_errors": exc.messages})


def _sale_queryset():
    return with_payment_totals(
        Sale.objects.select_related("customer", "sold_by", "voided_by")
    )


def _sale_detail(pk, context):
    sale = _sale_queryset().prefetch_related(
        "items__product", "items__allocations__batch", "payments__received_by"
    ).get(pk=pk)
    return SaleDetailSerializer(sale, context=context).data


class SaleFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    payment_status = django_filters.ChoiceFilter(
        choices=(("PAID", "Paid"), ("PARTIAL", "Partly paid"), ("UNPAID", "Unpaid"), ("VOID", "Void"))
    )
    # Only members of the active business (UserRole.objects is scoped), so the
    # filter can't be used to probe user ids from other businesses.
    sold_by = django_filters.ModelChoiceFilter(
        queryset=lambda request: User.objects.filter(memberships__in=UserRole.objects.all()).distinct()
    )
    receipt = django_filters.CharFilter(
        method="filter_receipt", label="Receipt number, e.g. S-000012 or 12."
    )

    class Meta:
        model = Sale
        fields = ("status", "customer")

    def filter_receipt(self, queryset, name, value):
        digits = re.sub(r"\D", "", value)
        return queryset.filter(number=int(digits)) if digits else queryset.none()


@extend_schema_view(
    list=extend_schema(tags=["sales"], summary="List sales"),
    retrieve=extend_schema(tags=["sales"], summary="Get a sale with its items and payments"),
    create=extend_schema(
        tags=["sales"],
        summary="Record a cash sale",
        description=(
            "One atomic transaction: checks stock, takes it from the batches that "
            "expire first, snapshots price and cost, and records the cash received. "
            "Cash short of the total stays owed and needs a customer."
        ),
        request=SaleCreateSerializer,
        responses={201: SaleDetailSerializer},
    ),
)
class SaleViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """FR-11 sales. Never edited or deleted; a mistake is voided."""

    required_permissions = SALES_PERMISSIONS
    filterset_class = SaleFilter
    search_fields = ("customer__name", "customer__phone", "note")
    ordering_fields = ("created_at", "number", "total", "balance")
    ordering = ("-created_at",)

    def get_queryset(self):
        return _sale_queryset()

    def get_serializer_class(self):
        if self.action == "create":
            return SaleCreateSerializer
        if self.action == "retrieve":
            return SaleDetailSerializer
        return SaleSerializer

    def retrieve(self, request, *args, **kwargs):
        sale = self.get_object()
        return Response(_sale_detail(sale.pk, self.get_serializer_context()))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        sale = _service_call(
            create_sale,
            user=request.user,
            lines=data["items"],
            customer=data["customer"],
            new_customer=data["new_customer"],
            amount_received=data["amount_received"],
            note=data["note"],
        )
        return Response(
            _sale_detail(sale.pk, self.get_serializer_context()), status=status.HTTP_201_CREATED
        )


class SaleActionView(generics.GenericAPIView):
    """Base for POST actions on one sale; another business's sale is a 404."""

    def get_queryset(self):
        return Sale.objects.all()

    def get_sale(self):
        return get_object_or_404(self.get_queryset(), pk=self.kwargs["pk"])


@extend_schema(
    tags=["sales"],
    summary="Record a payment towards what a sale still owes",
    request=PaymentCreateSerializer,
    responses={201: PaymentSerializer},
)
class SalePaymentView(SaleActionView):
    serializer_class = PaymentCreateSerializer
    required_permissions = (SALES_CREATE,)

    def post(self, request, pk):
        sale = self.get_sale()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = _service_call(
            record_payment, sale=sale, user=request.user, **serializer.validated_data
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["sales"],
    summary="Void a sale",
    description="Returns the stock to the batches it came from and refunds the cash collected. The sale stays on record as VOID.",
    request=VoidSerializer,
    responses={200: SaleDetailSerializer},
)
class SaleVoidView(SaleActionView):
    serializer_class = VoidSerializer
    required_permissions = (SALES_VOID,)

    def post(self, request, pk):
        sale = self.get_sale()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _service_call(void_sale, sale=sale, user=request.user, **serializer.validated_data)
        return Response(_sale_detail(sale.pk, self.get_serializer_context()))


@extend_schema(
    tags=["sales"],
    summary="Sales, profit and cash totals for a date range",
    parameters=[
        OpenApiParameter("date_from", OpenApiTypes.DATE, description="Default: today (Africa/Dar_es_Salaam)."),
        OpenApiParameter("date_to", OpenApiTypes.DATE, description="Default: date_from."),
    ],
    responses=SalesSummarySerializer,
)
class SalesSummaryView(generics.GenericAPIView):
    """FR-16/FR-17 dashboard figures."""

    serializer_class = SalesSummarySerializer
    required_permissions = (SALES_VIEW,)

    def get(self, request):
        date_from = self._date("date_from", timezone.localdate())
        date_to = self._date("date_to", date_from)
        if date_to < date_from:
            raise ValidationError({"date_to": ["The end date is before the start date."]})
        return Response(SalesSummarySerializer(sales_summary(date_from, date_to)).data)

    def _date(self, name, default):
        value = self.request.query_params.get(name)
        if not value:
            return default
        field = SalesSummarySerializer().fields["date_from"]
        try:
            return field.to_internal_value(value)
        except ValidationError:
            raise ValidationError({name: ["Use a date like 2026-10-10."]})


class CustomerFilter(django_filters.FilterSet):
    has_balance = django_filters.BooleanFilter(method="filter_has_balance", label="Only customers who owe money.")

    class Meta:
        model = Customer
        fields = ()

    def filter_has_balance(self, queryset, name, value):
        return queryset.filter(balance__gt=0) if value else queryset.filter(balance__lte=0)


@extend_schema_view(
    list=extend_schema(tags=["sales"], summary="List customers with what they owe"),
    retrieve=extend_schema(tags=["sales"], summary="Get a customer"),
    create=extend_schema(tags=["sales"], summary="Create a customer"),
    partial_update=extend_schema(tags=["sales"], summary="Update a customer"),
    destroy=extend_schema(
        tags=["sales"],
        summary="Delete a customer",
        responses={204: None, 409: OpenApiResponse(description="The customer has sales.")},
    ),
)
class CustomerViewSet(TenantModelViewSet):
    model = Customer
    serializer_class = CustomerSerializer
    required_permissions = CUSTOMER_PERMISSIONS
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    filterset_class = CustomerFilter
    search_fields = ("name", "phone")
    ordering_fields = ("name", "balance", "created_at")
    ordering = ("name",)
    protected_message = "This customer has sales and can't be deleted."

    def get_queryset(self):
        return with_customer_balance(Customer.objects.all())

    def _annotated(self, customer):
        return self.get_queryset().get(pk=customer.pk)

    def perform_create(self, serializer):
        serializer.instance = self._annotated(serializer.save())

    def perform_update(self, serializer):
        serializer.instance = self._annotated(serializer.save())
