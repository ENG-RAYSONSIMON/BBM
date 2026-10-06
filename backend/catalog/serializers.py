from rest_framework import serializers

from .models import Brand, Category, Product, Supplier


class UniqueInBusinessMixin:
    """Check per-business uniqueness that DRF can't derive from the model
    (constraints on Lower(name) or with a condition). Querysets go through the
    scoped manager, so only the active business is checked."""

    unique_case_insensitive = ()  # field names

    def validate(self, attrs):
        attrs = super().validate(attrs)
        model = self.Meta.model
        for field in self.unique_case_insensitive:
            value = attrs.get(field)
            if not value:
                continue
            clash = model.objects.filter(**{f"{field}__iexact": value})
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                label = model._meta.get_field(field).verbose_name
                raise serializers.ValidationError(
                    {field: [f"A {model._meta.verbose_name} with this {label} already exists."]}
                )
        return attrs


class CategorySerializer(UniqueInBusinessMixin, serializers.ModelSerializer):
    unique_case_insensitive = ("name",)

    class Meta:
        model = Category
        fields = ("id", "name", "description", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class BrandSerializer(UniqueInBusinessMixin, serializers.ModelSerializer):
    unique_case_insensitive = ("name",)

    class Meta:
        model = Brand
        fields = ("id", "name", "description", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class SupplierSerializer(UniqueInBusinessMixin, serializers.ModelSerializer):
    unique_case_insensitive = ("name",)

    class Meta:
        model = Supplier
        fields = (
            "id",
            "name",
            "contact_person",
            "phone",
            "email",
            "address",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class RefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class ProductSerializer(UniqueInBusinessMixin, serializers.ModelSerializer):
    """Read fields include derived stock (inventory.services.with_product_stock);
    the view always returns annotated instances."""

    unique_case_insensitive = ("sku", "barcode")

    # Default querysets come from the scoped manager: another business's id
    # is rejected as "does not exist" (NFR-7).
    category_detail = RefSerializer(source="category", read_only=True, allow_null=True)
    brand_detail = RefSerializer(source="brand", read_only=True, allow_null=True)
    supplier_detail = RefSerializer(source="supplier", read_only=True, allow_null=True)
    image = serializers.ImageField(read_only=True, allow_null=True)
    stock_on_hand = serializers.IntegerField(read_only=True)
    threshold = serializers.IntegerField(
        read_only=True, help_text="Effective low-stock threshold (reorder_level or the business default)."
    )
    stock_status = serializers.ChoiceField(choices=("out", "low", "in"), read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    nearest_expiry = serializers.DateField(read_only=True, allow_null=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "description",
            "sku",
            "barcode",
            "unit",
            "category",
            "category_detail",
            "brand",
            "brand_detail",
            "supplier",
            "supplier_detail",
            "selling_price",
            "cost_price",
            "reorder_level",
            "tracks_expiry",
            "image",
            "is_active",
            "stock_on_hand",
            "threshold",
            "stock_status",
            "is_low_stock",
            "nearest_expiry",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        extra_kwargs = {
            "selling_price": {"min_value": 0},
            "cost_price": {"min_value": 0},
        }

    def validate_tracks_expiry(self, value):
        product = self.instance
        if product is not None and product.tracks_expiry != value and product.batches.exists():
            raise serializers.ValidationError(
                "Can't change expiry tracking once the product has batches."
            )
        return value


class ProductImageSerializer(serializers.Serializer):
    # A plain FileField: catalog.validators owns every image check.
    image = serializers.FileField(
        help_text="JPEG, PNG or WebP, at most 2 MB and 4000×4000 px."
    )
