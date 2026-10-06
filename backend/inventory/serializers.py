from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from catalog.models import Product, ProductBatch

from .models import StockMovement
from .services import InsufficientStock, record_movement, resolve_batch


class BatchSerializer(serializers.ModelSerializer):
    stock_on_hand = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProductBatch
        fields = (
            "id",
            "product",
            "batch_number",
            "expiry_date",
            "received_on",
            "stock_on_hand",
            "created_at",
        )
        read_only_fields = ("id", "product", "created_at")

    def validate_batch_number(self, value):
        product = self.instance.product if self.instance else self.context["product"]
        clash = ProductBatch.objects.filter(product=product, batch_number__iexact=value)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("This product already has a batch with this number.")
        return value

    def validate(self, attrs):
        product = self.instance.product if self.instance else self.context["product"]
        expiry = attrs.get("expiry_date", getattr(self.instance, "expiry_date", None))
        if product.tracks_expiry and not expiry:
            raise serializers.ValidationError({"expiry_date": ["This product's batches need an expiry date."]})
        if not product.tracks_expiry and expiry:
            raise serializers.ValidationError(
                {"expiry_date": ["This product doesn't track expiry. Turn it on for the product first."]}
            )
        return attrs


class ExpiringBatchSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    stock_on_hand = serializers.IntegerField(read_only=True)
    days_left = serializers.SerializerMethodField()

    class Meta:
        model = ProductBatch
        fields = (
            "id",
            "product",
            "product_name",
            "batch_number",
            "expiry_date",
            "stock_on_hand",
            "days_left",
        )

    def get_days_left(self, batch) -> int:
        return (batch.expiry_date - timezone.localdate()).days


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    batch_number = serializers.CharField(source="batch.batch_number", read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = (
            "id",
            "product",
            "product_name",
            "batch",
            "batch_number",
            "movement_type",
            "quantity",
            "reason",
            "created_by",
            "created_by_name",
            "created_at",
        )
        read_only_fields = fields

    def get_created_by_name(self, movement) -> str:
        user = movement.created_by
        return user.get_full_name() or user.email


class StockAdjustmentSerializer(serializers.Serializer):
    """FR-7 manual stock change. Purchases and sales write their own
    movements from Phase 3; transfers wait for locations."""

    ALLOWED_TYPES = (
        StockMovement.Type.ADJUSTMENT,
        StockMovement.Type.DAMAGE,
        StockMovement.Type.EXPIRY,
    )

    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    batch = serializers.PrimaryKeyRelatedField(
        queryset=ProductBatch.objects.all(), required=False, allow_null=True,
        help_text="Existing batch. Omit to use or create one by batch_number.",
    )
    batch_number = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    expiry_date = serializers.DateField(required=False, allow_null=True, default=None)
    received_on = serializers.DateField(required=False, allow_null=True, default=None)
    movement_type = serializers.ChoiceField(choices=[(t.value, t.label) for t in ALLOWED_TYPES])
    quantity = serializers.IntegerField(
        help_text="Signed: positive adds stock, negative removes it. DAMAGE and EXPIRY must be negative."
    )
    reason = serializers.CharField(max_length=255)

    def validate(self, attrs):
        quantity = attrs["quantity"]
        if quantity == 0:
            raise serializers.ValidationError({"quantity": ["Enter a quantity other than 0."]})
        if attrs["movement_type"] in StockMovement.OUTBOUND and quantity > 0:
            raise serializers.ValidationError(
                {"quantity": ["Damage and expiry remove stock, so the quantity must be negative."]}
            )
        if quantity < 0 and attrs.get("batch") is None and attrs["product"].tracks_expiry:
            raise serializers.ValidationError({"batch": ["Choose the batch to remove stock from."]})
        return attrs

    def create(self, validated_data):
        product = validated_data["product"]
        try:
            # One transaction: a batch created here is rolled back if the
            # movement is refused.
            with transaction.atomic():
                batch = resolve_batch(
                    product,
                    batch=validated_data.get("batch"),
                    batch_number=validated_data["batch_number"].strip(),
                    expiry_date=validated_data["expiry_date"],
                    received_on=validated_data["received_on"],
                )
                return record_movement(
                    product=product,
                    batch=batch,
                    movement_type=validated_data["movement_type"],
                    quantity=validated_data["quantity"],
                    reason=validated_data["reason"],
                    user=self.context["request"].user,
                )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)
        except InsufficientStock as exc:
            raise serializers.ValidationError(
                {"quantity": [f"Only {exc.available} in stock in this batch."]}
            )


class InventorySummarySerializer(serializers.Serializer):
    low_stock = serializers.IntegerField()
    out_of_stock = serializers.IntegerField()
    expiring_soon = serializers.IntegerField()
    expired = serializers.IntegerField()
    expiry_warning_days = serializers.IntegerField()
