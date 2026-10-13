from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import Expense, ExpenseCategory

MONEY = {"max_digits": 12, "decimal_places": 2}


def _person(user) -> str:
    return (user.get_full_name() or user.email) if user else ""


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ("id", "name", "description", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_name(self, value):
        value = value.strip()
        clash = ExpenseCategory.objects.filter(name__iexact=value)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError(_("A category with this name already exists."))
        return value


class ExpenseSerializer(serializers.ModelSerializer):
    """The receipt file is managed through expenses/{id}/receipt/ and never
    exposed as a public URL."""

    category = serializers.PrimaryKeyRelatedField(queryset=ExpenseCategory.objects.all())
    category_name = serializers.CharField(source="category.name", read_only=True)
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))
    has_receipt = serializers.SerializerMethodField()
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = (
            "id",
            "category",
            "category_name",
            "amount",
            "expense_date",
            "description",
            "paid_to",
            "method",
            "has_receipt",
            "recorded_by",
            "recorded_by_name",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "method", "recorded_by", "created_at", "updated_at")

    def get_has_receipt(self, expense) -> bool:
        return bool(expense.receipt)

    def get_recorded_by_name(self, expense) -> str:
        return _person(expense.recorded_by)


class ReceiptUploadSerializer(serializers.Serializer):
    receipt = serializers.FileField(help_text="JPEG, PNG or WebP photo, or a PDF.")


class CategoryTotalSerializer(serializers.Serializer):
    category = serializers.UUIDField()
    category_name = serializers.CharField()
    total = serializers.DecimalField(**MONEY)
    count = serializers.IntegerField()


class ExpensesSummarySerializer(serializers.Serializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    total = serializers.DecimalField(**MONEY)
    count = serializers.IntegerField()
    by_category = CategoryTotalSerializer(many=True)
