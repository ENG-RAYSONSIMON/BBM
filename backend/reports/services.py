"""FR-18 reports. Read-only queries over the same data as the dashboard:
sale snapshots (never current prices) for revenue and cost, the payment
ledger for cash, expenses by date, and the stock ledger for what's on the
shelf. Every function returns {"rows": [...], "totals": {...}}."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import (
    Case,
    Count,
    DateField,
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    Subquery,
    Sum,
    When,
)
from django.db.models.functions import Coalesce, Round, Trunc
from django.utils import timezone

from catalog.models import Product, ProductBatch
from expenses.models import Expense
from inventory.services import with_batch_stock, with_product_stock
from purchases.models import PurchaseItem
from sales.models import Payment, Sale

ZERO = Decimal("0.00")
MONEY = DecimalField(max_digits=12, decimal_places=2)
VALUE = DecimalField(max_digits=16, decimal_places=2)
PERIODS = ("day", "week", "month", "year")


# ---- periods -------------------------------------------------------------------

def period_start(day, period):
    """First day of the period holding `day`. Weeks start on Monday."""
    if period == "week":
        return day - timedelta(days=day.weekday())
    if period == "month":
        return day.replace(day=1)
    if period == "year":
        return day.replace(month=1, day=1)
    return day


def _next_start(start, period):
    if period == "week":
        return start + timedelta(days=7)
    if period == "month":
        return (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    if period == "year":
        return start.replace(year=start.year + 1)
    return start + timedelta(days=1)


def period_starts(date_from, date_to, period):
    """Every period from the one holding date_from to the one holding
    date_to, so empty periods show as zeros."""
    starts, start = [], period_start(date_from, period)
    while start <= date_to:
        starts.append(start)
        start = _next_start(start, period)
    return starts


def _bucket(field, period):
    # Truncated in the shop's time zone (Africa/Dar_es_Salaam), as a date.
    return Trunc(field, period, output_field=DateField())


def _grouped(queryset, field, period, **sums):
    """{period start: {name: sum}} for the queryset, grouped by period."""
    rows = (
        queryset.order_by()
        .annotate(period=_bucket(field, period))
        .values("period")
        .annotate(**sums)
    )
    return {row.pop("period"): row for row in rows}


def _sum_totals(rows, keys):
    return {key: sum((row[key] for row in rows), start=0 if key.endswith("count") else ZERO) for key in keys}


# ---- time-based reports -------------------------------------------------------------

def _completed_sales(date_from, date_to):
    return Sale.objects.filter(
        status=Sale.Status.COMPLETED, created_at__date__gte=date_from, created_at__date__lte=date_to
    )


def _sales_by_period(date_from, date_to, period):
    return _grouped(
        _completed_sales(date_from, date_to),
        "created_at",
        period,
        sales_count=Count("id"),
        revenue=Sum("total"),
        discounts=Sum("discount_total"),
        cogs=Sum("cost_total"),
    )


def _expenses_in(date_from, date_to):
    return Expense.objects.filter(expense_date__gte=date_from, expense_date__lte=date_to)


def sales_report(date_from, date_to, period):
    """Per period: completed sales (voids left out), revenue, discounts, cost
    of goods sold and gross profit from the sale snapshots, and cash
    collected (payments − refunds) in that period."""
    sales = _sales_by_period(date_from, date_to, period)
    cash = _grouped(
        Payment.objects.filter(created_at__date__gte=date_from, created_at__date__lte=date_to),
        "created_at",
        period,
        net=Sum(Case(When(kind=Payment.Kind.REFUND, then=-F("amount")), default=F("amount"), output_field=MONEY)),
    )
    rows = []
    for start in period_starts(date_from, date_to, period):
        row = sales.get(start, {})
        revenue, cogs = row.get("revenue") or ZERO, row.get("cogs") or ZERO
        rows.append(
            {
                "period": start,
                "sales_count": row.get("sales_count", 0),
                "revenue": revenue,
                "discounts": row.get("discounts") or ZERO,
                "cogs": cogs,
                "gross_profit": revenue - cogs,
                "cash_collected": cash.get(start, {}).get("net") or ZERO,
            }
        )
    keys = ("sales_count", "revenue", "discounts", "cogs", "gross_profit", "cash_collected")
    return {"rows": rows, "totals": _sum_totals(rows, keys)}


def profit_report(date_from, date_to, period):
    """Per period: gross profit (revenue − cost of goods sold) minus the
    expenses dated in that period gives net profit."""
    sales = _sales_by_period(date_from, date_to, period)
    expenses = _grouped(_expenses_in(date_from, date_to), "expense_date", period, total=Sum("amount"))
    rows = []
    for start in period_starts(date_from, date_to, period):
        row = sales.get(start, {})
        revenue, cogs = row.get("revenue") or ZERO, row.get("cogs") or ZERO
        spent = expenses.get(start, {}).get("total") or ZERO
        rows.append(
            {
                "period": start,
                "revenue": revenue,
                "cogs": cogs,
                "gross_profit": revenue - cogs,
                "expenses": spent,
                "net_profit": revenue - cogs - spent,
            }
        )
    keys = ("revenue", "cogs", "gross_profit", "expenses", "net_profit")
    return {"rows": rows, "totals": _sum_totals(rows, keys)}


def expenses_report(date_from, date_to, period):
    """Per period and category (only those with spending), largest first
    within each period."""
    grouped = (
        _expenses_in(date_from, date_to)
        .order_by()
        .annotate(period=_bucket("expense_date", period))
        .values("period", "category", "category__name")
        .annotate(count=Count("id"), total=Sum("amount"))
        .order_by("period", "-total", "category__name")
    )
    rows = [
        {
            "period": row["period"],
            "category": row["category"],
            "category_name": row["category__name"],
            "count": row["count"],
            "total": row["total"],
        }
        for row in grouped
    ]
    return {"rows": rows, "totals": _sum_totals(rows, ("count", "total"))}


# ---- stock reports ---------------------------------------------------------------

def with_batch_cost(batches):
    """Annotate unit_cost: what each batch cost, i.e. the average paid on the
    received purchases that filled it (Σ line_total / Σ quantity; a line's
    batch is set only on receiving). Stock with no purchase behind it
    (opening stock, adjustments) falls back to the product's cost price."""
    paid = (
        PurchaseItem.objects.filter(batch=OuterRef("pk"))
        .order_by()
        .values("batch")
        .annotate(cost=Round(Sum("line_total") / Sum("quantity"), 2))
        .values("cost")
    )
    return batches.annotate(
        unit_cost=Coalesce(Subquery(paid, output_field=MONEY), F("product__cost_price"), output_field=MONEY)
    )


def _cost_values_by_product():
    """{product id: Σ batch stock × batch cost} over batches holding stock."""
    batches = with_batch_cost(with_batch_stock(ProductBatch.objects.all())).filter(stock_on_hand__gt=0)
    values = defaultdict(lambda: ZERO)
    for batch in batches.values("product", "stock_on_hand", "unit_cost"):
        values[batch["product"]] += batch["stock_on_hand"] * batch["unit_cost"]
    return values


def stock_valuation_report():
    """Every product that holds stock (archived ones too), valued at what
    each of its batches cost (see with_batch_cost) and at its current
    selling price."""
    cost_values = _cost_values_by_product()
    products = (
        with_product_stock(Product.objects.select_related("category"))
        .filter(stock_on_hand__gt=0)
        .annotate(
            retail_value=ExpressionWrapper(F("stock_on_hand") * F("selling_price"), output_field=VALUE),
        )
        .order_by("name")
    )
    rows = [
        {
            "product": p.pk,
            "name": p.name,
            "sku": p.sku,
            "category_name": p.category.name if p.category else "",
            "unit": p.unit,
            "is_active": p.is_active,
            "stock_on_hand": p.stock_on_hand,
            "cost_price": p.cost_price,
            "selling_price": p.selling_price,
            "cost_value": cost_values[p.pk],
            "retail_value": p.retail_value,
        }
        for p in products
    ]
    totals = _sum_totals(rows, ("cost_value", "retail_value"))
    totals.update(product_count=len(rows), stock_on_hand=sum(row["stock_on_hand"] for row in rows))
    return {"as_of": timezone.localdate(), "rows": rows, "totals": totals}


def expiry_report(within_days, today=None):
    """Batches that still hold stock and are expired or expire within
    `within_days`, soonest first, valued at what each batch cost (see
    with_batch_cost). Archived products are included: their expired stock
    still needs writing off."""
    today = today or timezone.localdate()
    batches = with_batch_cost(
        with_batch_stock(
            ProductBatch.objects.filter(
                expiry_date__isnull=False,
                expiry_date__lte=today + timedelta(days=within_days),
            )
        )
    ).filter(stock_on_hand__gt=0).select_related("product").order_by("expiry_date", "product__name")
    rows = []
    for batch in batches:
        cost_value = batch.stock_on_hand * batch.unit_cost
        rows.append(
            {
                "batch": batch.pk,
                "product": batch.product_id,
                "name": batch.product.name,
                "sku": batch.product.sku,
                "batch_number": batch.batch_number,
                "expiry_date": batch.expiry_date,
                "days_left": (batch.expiry_date - today).days,
                "status": "expired" if batch.expiry_date < today else "expiring",
                "is_active": batch.product.is_active,
                "stock_on_hand": batch.stock_on_hand,
                "cost_price": batch.unit_cost,
                "cost_value": cost_value,
            }
        )
    expired = [row for row in rows if row["status"] == "expired"]
    totals = {
        "batch_count": len(rows),
        "stock_on_hand": sum(row["stock_on_hand"] for row in rows),
        "cost_value": sum((row["cost_value"] for row in rows), start=ZERO),
        "expired_value": sum((row["cost_value"] for row in expired), start=ZERO),
    }
    return {"as_of": today, "within_days": within_days, "rows": rows, "totals": totals}
