import django_filters
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, mixins, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.models import BusinessSettings
from accounts.rbac import INVENTORY_ADJUST, INVENTORY_VIEW
from catalog.models import Product, ProductBatch
from catalog.serializers import ProductSerializer

from .models import StockMovement
from .serializers import (
    BatchSerializer,
    ExpiringBatchSerializer,
    InventorySummarySerializer,
    StockAdjustmentSerializer,
    StockMovementSerializer,
)
from .services import expiring_batches, inventory_summary, with_batch_stock, with_product_stock

INVENTORY_PERMISSIONS = {
    "GET": (INVENTORY_VIEW,),
    "POST": (INVENTORY_ADJUST,),
    "PATCH": (INVENTORY_ADJUST,),
}


@extend_schema_view(
    get=extend_schema(tags=["inventory"], summary="List a product's batches with stock"),
    post=extend_schema(tags=["inventory"], summary="Create a batch for a product"),
)
class ProductBatchListView(generics.ListCreateAPIView):
    serializer_class = BatchSerializer
    required_permissions = INVENTORY_PERMISSIONS
    filter_backends = ()  # a product rarely has many batches; keep it simple
    ordering = ("expiry_date", "batch_number")

    def get_product(self):
        if not hasattr(self, "_product"):
            # Scoped manager: another business's product is a 404.
            self._product = get_object_or_404(Product.objects.all(), pk=self.kwargs["product_id"])
        return self._product

    def get_queryset(self):
        return with_batch_stock(ProductBatch.objects.filter(product=self.get_product())).order_by(
            *self.ordering
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if "product_id" in self.kwargs:
            context["product"] = self.get_product()
        return context

    def perform_create(self, serializer):
        batch = serializer.save(product=self.get_product())
        serializer.instance = with_batch_stock(ProductBatch.objects.all()).get(pk=batch.pk)


@extend_schema_view(
    get=extend_schema(tags=["inventory"], summary="Get a batch"),
    patch=extend_schema(tags=["inventory"], summary="Update a batch number or expiry date"),
)
class BatchDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = BatchSerializer
    required_permissions = INVENTORY_PERMISSIONS
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return with_batch_stock(ProductBatch.objects.select_related("product"))

    def perform_update(self, serializer):
        batch = serializer.save()
        serializer.instance = self.get_queryset().get(pk=batch.pk)


class StockMovementFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")

    class Meta:
        model = StockMovement
        fields = ("product", "batch", "movement_type")


@extend_schema_view(
    list=extend_schema(tags=["inventory"], summary="List stock movements (the ledger)"),
    retrieve=extend_schema(tags=["inventory"], summary="Get a stock movement"),
    create=extend_schema(
        tags=["inventory"],
        summary="Record a stock adjustment",
        request=StockAdjustmentSerializer,
        responses={201: StockMovementSerializer},
    ),
)
class StockMovementViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """FR-7 ledger. Rows are never edited or deleted; corrections are new
    adjustment rows."""

    required_permissions = INVENTORY_PERMISSIONS
    filterset_class = StockMovementFilter
    search_fields = ("product__name", "batch__batch_number", "reason")
    ordering_fields = ("created_at", "quantity")
    ordering = ("-created_at",)

    def get_queryset(self):
        return StockMovement.objects.select_related("product", "batch", "created_by")

    def get_serializer_class(self):
        return StockAdjustmentSerializer if self.action == "create" else StockMovementSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        movement = serializer.save()
        movement = self.get_queryset().get(pk=movement.pk)
        return Response(
            StockMovementSerializer(movement, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["inventory"], summary="Active products at or below their low-stock threshold")
class LowStockView(generics.ListAPIView):
    """FR-9. Includes out-of-stock products, lowest stock first."""

    serializer_class = ProductSerializer
    required_permissions = (INVENTORY_VIEW,)
    filterset_fields = ("category", "brand", "supplier")
    search_fields = ("name", "sku", "barcode")
    ordering_fields = ("stock_on_hand", "name")
    ordering = ("stock_on_hand", "name")

    def get_queryset(self):
        return with_product_stock(
            Product.objects.filter(is_active=True).select_related("category", "brand", "supplier")
        ).filter(is_low_stock=True)


@extend_schema(
    tags=["inventory"],
    summary="Batches with stock that are expired or expire soon",
    parameters=[
        OpenApiParameter(
            "within", OpenApiTypes.INT, description="Days ahead (1–365). Default: the business's expiry warning setting."
        ),
        OpenApiParameter("expired", OpenApiTypes.BOOL, description="Only already-expired batches."),
    ],
)
class ExpiringView(generics.ListAPIView):
    """FR-9 expiry views (7/30/60-day, expired). Only batches that still hold
    stock are listed, soonest first."""

    serializer_class = ExpiringBatchSerializer
    required_permissions = (INVENTORY_VIEW,)
    filterset_fields = ("product__category", "product__brand", "product__supplier")
    search_fields = ("product__name", "batch_number")
    ordering_fields = ("expiry_date",)
    ordering = ("expiry_date", "product__name")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation
            return ProductBatch.objects.none()
        params = self.request.query_params
        if params.get("expired") in ("1", "true", "True"):
            return expiring_batches(expired=True).select_related("product")
        within = params.get("within")
        if within is None:
            days = BusinessSettings.objects.values_list("expiry_warning_days", flat=True).get()
        else:
            try:
                days = int(within)
            except ValueError:
                days = -1
            if not 1 <= days <= 365:
                raise ValidationError({"within": ["Use a whole number of days from 1 to 365."]})
        return expiring_batches(within_days=days).select_related("product")


@extend_schema(tags=["inventory"], summary="Stock alert counts for the dashboard", responses=InventorySummarySerializer)
class InventorySummaryView(generics.GenericAPIView):
    serializer_class = InventorySummarySerializer
    required_permissions = (INVENTORY_VIEW,)

    def get(self, request):
        return Response(InventorySummarySerializer(inventory_summary()).data)
