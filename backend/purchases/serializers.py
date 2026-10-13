from rest_framework import serializers

from catalog.models import Product, Supplier

from .models import Purchase, PurchaseItem

MONEY = {"max_digits": 12, "decimal_places": 2}


def _person(user) -> str:
    return (user.get_full_name() or user.email) if user else ""


class PurchaseLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.IntegerField(min_value=1)
    unit_cost = serializers.DecimalField(**MONEY, min_value=0, help_text="Cost per unit paid to the supplier.")
    batch_number = serializers.CharField(
        max_length=64, required=False, allow_blank=True, default="",
        help_text="Required for products that track expiry.",
    )
    expiry_date = serializers.DateField(
        required=False, allow_null=True, default=None,
        help_text="Required when the batch is new and the product tracks expiry.",
    )


class PurchaseWriteSerializer(serializers.Serializer):
    """Create or replace a draft. Status and totals are set by the server."""

    supplier = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects.all(), required=False, allow_null=True, default=None
    )
    reference = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    purchase_date = serializers.DateField(required=False, allow_null=True, default=None)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    items = PurchaseLineInputSerializer(many=True, allow_empty=False)


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class PurchaseItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    tracks_expiry = serializers.BooleanField(source="product.tracks_expiry", read_only=True)

    class Meta:
        model = PurchaseItem
        fields = (
            "id",
            "product",
            "product_name",
            "tracks_expiry",
            "quantity",
            "unit_cost",
            "line_total",
            "batch_number",
            "expiry_date",
            "batch",
        )
        read_only_fields = fields


class PurchaseSerializer(serializers.ModelSerializer):
    """List view of a purchase."""

    purchase_number = serializers.CharField(read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default=None)
    created_by_name = serializers.SerializerMethodField()
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Purchase
        fields = (
            "id",
            "number",
            "purchase_number",
            "status",
            "supplier",
            "supplier_name",
            "reference",
            "purchase_date",
            "note",
            "total",
            "item_count",
            "created_by",
            "created_by_name",
            "received_at",
            "created_at",
        )
        read_only_fields = fields

    def get_created_by_name(self, purchase) -> str:
        return _person(purchase.created_by)


class PurchaseDetailSerializer(PurchaseSerializer):
    items = PurchaseItemSerializer(many=True, read_only=True)
    received_by_name = serializers.SerializerMethodField()
    cancelled_by_name = serializers.SerializerMethodField()

    class Meta(PurchaseSerializer.Meta):
        fields = (
            *PurchaseSerializer.Meta.fields,
            "items",
            "received_by",
            "received_by_name",
            "cancelled_at",
            "cancelled_by",
            "cancelled_by_name",
            "cancel_reason",
        )
        read_only_fields = fields

    def get_received_by_name(self, purchase) -> str:
        return _person(purchase.received_by)

    def get_cancelled_by_name(self, purchase) -> str:
        return _person(purchase.cancelled_by)
