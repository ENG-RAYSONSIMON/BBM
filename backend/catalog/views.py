import uuid

import django_filters
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from accounts.rbac import CATALOG_DELETE, CATALOG_MANAGE, CATALOG_VIEW
from core.views import Conflict, TenantModelViewSet
from inventory.services import with_product_stock

from .models import Brand, Category, Product, Supplier
from .serializers import (
    BrandSerializer,
    CategorySerializer,
    ProductImageSerializer,
    ProductSerializer,
    SupplierSerializer,
)
from .validators import validate_product_image

CATALOG_PERMISSIONS = {
    "GET": (CATALOG_VIEW,),
    "POST": (CATALOG_MANAGE,),
    "PUT": (CATALOG_MANAGE,),
    "PATCH": (CATALOG_MANAGE,),
    "DELETE": (CATALOG_DELETE,),
}

IN_USE = OpenApiResponse(description="Still referenced by other records.")


def _crud_schema(noun):
    return extend_schema_view(
        list=extend_schema(tags=["catalog"], summary=f"List {noun}s"),
        retrieve=extend_schema(tags=["catalog"], summary=f"Get a {noun}"),
        create=extend_schema(tags=["catalog"], summary=f"Create a {noun}"),
        update=extend_schema(tags=["catalog"], summary=f"Replace a {noun}"),
        partial_update=extend_schema(tags=["catalog"], summary=f"Update a {noun}"),
        destroy=extend_schema(tags=["catalog"], summary=f"Delete a {noun}", responses={204: None, 409: IN_USE}),
    )


@_crud_schema("category")
class CategoryViewSet(TenantModelViewSet):
    model = Category
    serializer_class = CategorySerializer
    required_permissions = CATALOG_PERMISSIONS
    search_fields = ("name",)
    ordering_fields = ("name", "created_at")
    protected_message = "This category still has products. Move them to another category first."


@_crud_schema("brand")
class BrandViewSet(TenantModelViewSet):
    model = Brand
    serializer_class = BrandSerializer
    required_permissions = CATALOG_PERMISSIONS
    search_fields = ("name",)
    ordering_fields = ("name", "created_at")
    protected_message = "This brand still has products. Move them to another brand first."


@_crud_schema("supplier")
class SupplierViewSet(TenantModelViewSet):
    model = Supplier
    serializer_class = SupplierSerializer
    required_permissions = CATALOG_PERMISSIONS
    search_fields = ("name", "contact_person", "phone", "email")
    ordering_fields = ("name", "created_at")
    protected_message = "This supplier still has products. Move them to another supplier first."


class ProductFilter(django_filters.FilterSet):
    stock_status = django_filters.ChoiceFilter(
        choices=(("out", "Out of stock"), ("low", "Low stock (includes out)"), ("in", "In stock")),
        method="filter_stock_status",
    )

    class Meta:
        model = Product
        fields = ("category", "brand", "supplier", "is_active", "tracks_expiry")

    def filter_stock_status(self, queryset, name, value):
        if value == "low":
            return queryset.filter(is_low_stock=True)
        return queryset.filter(stock_status=value)


@_crud_schema("product")
class ProductViewSet(TenantModelViewSet):
    """FR-6 products. Every response carries derived stock (FR-8). A product
    with stock history can't be deleted; archive it with is_active=false."""

    model = Product
    serializer_class = ProductSerializer
    required_permissions = CATALOG_PERMISSIONS
    filterset_class = ProductFilter
    search_fields = ("name", "sku", "barcode")
    ordering_fields = ("name", "selling_price", "stock_on_hand", "nearest_expiry", "created_at")
    ordering = ("name",)

    def get_queryset(self):
        return with_product_stock(
            Product.objects.select_related("category", "brand", "supplier")
        )

    def _annotated(self, product):
        return self.get_queryset().get(pk=product.pk)

    def perform_create(self, serializer):
        serializer.instance = self._annotated(serializer.save())

    def perform_update(self, serializer):
        serializer.instance = self._annotated(serializer.save())

    @transaction.atomic
    def perform_destroy(self, instance):
        if instance.stock_movements.exists():
            raise Conflict("This product has stock history and can't be deleted. Archive it instead.")
        storage, image_name = instance.image.storage, instance.image.name
        instance.batches.all().delete()  # empty batches only: no movements
        instance.delete()
        if image_name:
            transaction.on_commit(lambda: storage.delete(image_name))


class ProductImageView(generics.GenericAPIView):
    """FR-10: upload (replace) or remove a product's image."""

    serializer_class = ProductImageSerializer
    parser_classes = (MultiPartParser,)
    required_permissions = (CATALOG_MANAGE,)

    def get_queryset(self):
        return Product.objects.all()

    @extend_schema(
        tags=["catalog"],
        summary="Upload a product image",
        request={"multipart/form-data": ProductImageSerializer},
        responses={200: ProductSerializer, 400: OpenApiResponse(description="Invalid image.")},
    )
    def put(self, request, pk):
        product = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["image"]
        try:
            extension = validate_product_image(upload)
        except DjangoValidationError as exc:
            raise ValidationError({"image": exc.messages})

        old_name = product.image.name if product.image else None
        with transaction.atomic():
            product.image.save(f"{uuid.uuid4().hex}.{extension}", upload, save=True)
        if old_name:
            product.image.storage.delete(old_name)
        return Response(self._product_data(product))

    @extend_schema(tags=["catalog"], summary="Remove a product image", request=None, responses={200: ProductSerializer})
    def delete(self, request, pk):
        product = self.get_object()
        if product.image:
            storage, name = product.image.storage, product.image.name
            product.image = None
            product.save(update_fields=["image", "updated_at"])
            storage.delete(name)
        return Response(self._product_data(product))

    def _product_data(self, product):
        annotated = with_product_stock(Product.objects.all()).get(pk=product.pk)
        return ProductSerializer(annotated, context=self.get_serializer_context()).data
