from rest_framework import serializers

from catalog.models import Product

from .models import Customer, Payment, Sale, SaleItem, SaleItemAllocation

MONEY = {"max_digits": 12, "decimal_places": 2}


def _person(user) -> str:
    return (user.get_full_name() or user.email) if user else ""


def _phone_taken(phone, exclude=None):
    clash = Customer.objects.filter(phone=phone)
    if exclude is not None:
        clash = clash.exclude(pk=exclude.pk)
    return phone and clash.exists()


class CustomerSerializer(serializers.ModelSerializer):
    total_bought = serializers.DecimalField(**MONEY, read_only=True)
    amount_paid = serializers.DecimalField(**MONEY, read_only=True)
    balance = serializers.DecimalField(**MONEY, read_only=True, help_text="Still owed on credit sales.")

    class Meta:
        model = Customer
        fields = (
            "id",
            "name",
            "phone",
            "notes",
            "total_bought",
            "amount_paid",
            "balance",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_phone(self, value):
        value = value.strip()
        if _phone_taken(value, exclude=self.instance):
            raise serializers.ValidationError("A customer with this phone number already exists.")
        return value


class NewCustomerSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")

    def validate_phone(self, value):
        value = value.strip()
        if _phone_taken(value):
            raise serializers.ValidationError(
                "A customer with this phone number already exists. Choose them instead."
            )
        return value


class SaleLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.IntegerField(min_value=1)
    discount = serializers.DecimalField(
        **MONEY, min_value=0, required=False, default=0,
        help_text="Discount on the whole line, in TZS.",
    )


class SaleCreateSerializer(serializers.Serializer):
    """FR-11 input. Prices and costs come from the products, never from the
    client."""

    items = SaleLineInputSerializer(many=True, allow_empty=False)
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(), required=False, allow_null=True, default=None
    )
    new_customer = NewCustomerSerializer(
        required=False, allow_null=True, default=None,
        help_text="Create the customer with the sale. Use instead of `customer`.",
    )
    amount_received = serializers.DecimalField(
        **MONEY, min_value=0, help_text="Cash handed over. Less than the total leaves a balance owed."
    )
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs.get("customer") and attrs.get("new_customer"):
            raise serializers.ValidationError(
                {"new_customer": ["Choose an existing customer or enter a new one, not both."]}
            )
        return attrs


class PaymentCreateSerializer(serializers.Serializer):
    amount_received = serializers.DecimalField(**MONEY, min_value=0)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class VoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class PaymentSerializer(serializers.ModelSerializer):
    received_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = (
            "id",
            "kind",
            "method",
            "amount",
            "amount_received",
            "change_given",
            "received_by",
            "received_by_name",
            "note",
            "created_at",
        )
        read_only_fields = fields

    def get_received_by_name(self, payment) -> str:
        return _person(payment.received_by)


class AllocationSerializer(serializers.ModelSerializer):
    batch_number = serializers.CharField(source="batch.batch_number", read_only=True)
    expiry_date = serializers.DateField(source="batch.expiry_date", read_only=True)

    class Meta:
        model = SaleItemAllocation
        fields = ("batch", "batch_number", "expiry_date", "quantity")
        read_only_fields = fields


class SaleItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    allocations = AllocationSerializer(many=True, read_only=True)

    class Meta:
        model = SaleItem
        fields = (
            "id",
            "product",
            "product_name",
            "quantity",
            "unit_price",
            "discount",
            "line_total",
            "unit_cost",
            "line_cost",
            "allocations",
        )
        read_only_fields = fields


class SaleSerializer(serializers.ModelSerializer):
    """List view of a sale, with derived payment totals."""

    receipt_number = serializers.CharField(read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True, default=None)
    sold_by_name = serializers.SerializerMethodField()
    gross_profit = serializers.DecimalField(**MONEY, read_only=True)
    amount_paid = serializers.DecimalField(**MONEY, read_only=True)
    balance = serializers.DecimalField(**MONEY, read_only=True)
    payment_status = serializers.ChoiceField(
        choices=("PAID", "PARTIAL", "UNPAID", "VOID"), read_only=True
    )

    class Meta:
        model = Sale
        fields = (
            "id",
            "number",
            "receipt_number",
            "status",
            "customer",
            "customer_name",
            "customer_phone",
            "sold_by",
            "sold_by_name",
            "subtotal",
            "discount_total",
            "total",
            "cost_total",
            "gross_profit",
            "amount_paid",
            "balance",
            "payment_status",
            "note",
            "created_at",
        )
        read_only_fields = fields

    def get_sold_by_name(self, sale) -> str:
        return _person(sale.sold_by)


class SaleDetailSerializer(SaleSerializer):
    items = SaleItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    voided_by_name = serializers.SerializerMethodField()

    class Meta(SaleSerializer.Meta):
        fields = (
            *SaleSerializer.Meta.fields,
            "items",
            "payments",
            "voided_at",
            "voided_by",
            "voided_by_name",
            "void_reason",
        )
        read_only_fields = fields

    def get_voided_by_name(self, sale) -> str:
        return _person(sale.voided_by)


class SalesSummarySerializer(serializers.Serializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    sales_count = serializers.IntegerField()
    revenue = serializers.DecimalField(**MONEY)
    discounts = serializers.DecimalField(**MONEY)
    cogs = serializers.DecimalField(**MONEY)
    gross_profit = serializers.DecimalField(**MONEY)
    cash_collected = serializers.DecimalField(**MONEY, help_text="Payments − refunds in the range.")
    outstanding_credit = serializers.DecimalField(**MONEY, help_text="Still owed on all sales, all time.")
