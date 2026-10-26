from datetime import date, timedelta

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .services import PERIODS

MONEY = {"max_digits": 12, "decimal_places": 2}
VALUE = {"max_digits": 16, "decimal_places": 2}
# A daily report of more than about a year is unreadable; use a longer period.
MAX_DAILY_DAYS = 366
# Bounds that keep every report small and its date maths in range.
EARLIEST = date(2000, 1, 1)
MAX_SPAN_DAYS = 10 * 366


class PeriodQuerySerializer(serializers.Serializer):
    period = serializers.ChoiceField(choices=PERIODS, default="day")
    date_from = serializers.DateField(required=False, help_text="Default: 29 days before date_to.")
    date_to = serializers.DateField(required=False, help_text="Default: today (Africa/Dar_es_Salaam).")

    def validate(self, attrs):
        latest = timezone.localdate() + timedelta(days=366)
        for name in ("date_from", "date_to"):
            if name in attrs and not EARLIEST <= attrs[name] <= latest:
                raise serializers.ValidationError({name: [_("Pick a date between 2000 and next year.")]})
        attrs.setdefault("date_to", timezone.localdate())
        attrs.setdefault("date_from", max(EARLIEST, attrs["date_to"] - timedelta(days=29)))
        if attrs["date_to"] < attrs["date_from"]:
            raise serializers.ValidationError({"date_to": [_("The end date is before the start date.")]})
        if (attrs["date_to"] - attrs["date_from"]).days >= MAX_SPAN_DAYS:
            raise serializers.ValidationError({"date_from": [_("That range is too long. Pick 10 years or less.")]})
        if attrs["period"] == "day" and (attrs["date_to"] - attrs["date_from"]).days >= MAX_DAILY_DAYS:
            raise serializers.ValidationError(
                {"period": [_("That is too many days. Show it by week, month or year instead.")]}
            )
        return attrs


class ExpiryQuerySerializer(serializers.Serializer):
    within_days = serializers.IntegerField(min_value=1, max_value=365, default=60)


class PeriodReportSerializer(serializers.Serializer):
    period = serializers.ChoiceField(choices=PERIODS)
    date_from = serializers.DateField()
    date_to = serializers.DateField()


class SalesRowSerializer(serializers.Serializer):
    period = serializers.DateField(help_text="First day of the period (weeks start on Monday).")
    sales_count = serializers.IntegerField()
    revenue = serializers.DecimalField(**MONEY)
    discounts = serializers.DecimalField(**MONEY)
    cogs = serializers.DecimalField(**MONEY, help_text="Cost of goods sold, from the sale snapshots.")
    gross_profit = serializers.DecimalField(**MONEY)
    cash_collected = serializers.DecimalField(**MONEY, help_text="Payments − refunds received in the period.")


class SalesTotalsSerializer(serializers.Serializer):
    sales_count = serializers.IntegerField()
    revenue = serializers.DecimalField(**MONEY)
    discounts = serializers.DecimalField(**MONEY)
    cogs = serializers.DecimalField(**MONEY)
    gross_profit = serializers.DecimalField(**MONEY)
    cash_collected = serializers.DecimalField(**MONEY)


class SalesReportSerializer(PeriodReportSerializer):
    rows = SalesRowSerializer(many=True)
    totals = SalesTotalsSerializer()


class ProfitRowSerializer(serializers.Serializer):
    period = serializers.DateField()
    revenue = serializers.DecimalField(**MONEY)
    cogs = serializers.DecimalField(**MONEY)
    gross_profit = serializers.DecimalField(**MONEY)
    expenses = serializers.DecimalField(**MONEY)
    net_profit = serializers.DecimalField(**MONEY)


class ProfitTotalsSerializer(serializers.Serializer):
    revenue = serializers.DecimalField(**MONEY)
    cogs = serializers.DecimalField(**MONEY)
    gross_profit = serializers.DecimalField(**MONEY)
    expenses = serializers.DecimalField(**MONEY)
    net_profit = serializers.DecimalField(**MONEY)


class ProfitReportSerializer(PeriodReportSerializer):
    rows = ProfitRowSerializer(many=True)
    totals = ProfitTotalsSerializer()


class ExpensesRowSerializer(serializers.Serializer):
    period = serializers.DateField()
    category = serializers.UUIDField()
    category_name = serializers.CharField()
    count = serializers.IntegerField()
    total = serializers.DecimalField(**MONEY)


class ExpensesTotalsSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    total = serializers.DecimalField(**MONEY)


class ExpensesReportSerializer(PeriodReportSerializer):
    rows = ExpensesRowSerializer(many=True)
    totals = ExpensesTotalsSerializer()


LATEST_COST = "At the product's latest cost price, not each batch's own cost."


class StockValuationRowSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    name = serializers.CharField()
    sku = serializers.CharField()
    category_name = serializers.CharField()
    unit = serializers.CharField()
    is_active = serializers.BooleanField()
    stock_on_hand = serializers.IntegerField()
    cost_price = serializers.DecimalField(**MONEY)
    selling_price = serializers.DecimalField(**MONEY)
    cost_value = serializers.DecimalField(**VALUE, help_text=LATEST_COST)
    retail_value = serializers.DecimalField(**VALUE)


class StockValuationTotalsSerializer(serializers.Serializer):
    product_count = serializers.IntegerField()
    stock_on_hand = serializers.IntegerField()
    cost_value = serializers.DecimalField(**VALUE)
    retail_value = serializers.DecimalField(**VALUE)


class StockValuationReportSerializer(serializers.Serializer):
    as_of = serializers.DateField()
    rows = StockValuationRowSerializer(many=True)
    totals = StockValuationTotalsSerializer()


class ExpiryRowSerializer(serializers.Serializer):
    batch = serializers.UUIDField()
    product = serializers.UUIDField()
    name = serializers.CharField()
    sku = serializers.CharField()
    batch_number = serializers.CharField()
    expiry_date = serializers.DateField()
    days_left = serializers.IntegerField(help_text="Negative once expired.")
    status = serializers.ChoiceField(choices=("expired", "expiring"))
    is_active = serializers.BooleanField()
    stock_on_hand = serializers.IntegerField()
    cost_price = serializers.DecimalField(**MONEY, help_text=LATEST_COST)
    cost_value = serializers.DecimalField(**VALUE, help_text=LATEST_COST)


class ExpiryTotalsSerializer(serializers.Serializer):
    batch_count = serializers.IntegerField()
    stock_on_hand = serializers.IntegerField()
    cost_value = serializers.DecimalField(**VALUE, help_text=LATEST_COST)
    expired_value = serializers.DecimalField(**VALUE, help_text=LATEST_COST)


class ExpiryReportSerializer(serializers.Serializer):
    as_of = serializers.DateField()
    within_days = serializers.IntegerField()
    rows = ExpiryRowSerializer(many=True)
    totals = ExpiryTotalsSerializer()
