"""Expenses (FR-15) and their totals for net profit (FR-16)."""

from decimal import Decimal

from django.db.models import Count, DecimalField, Sum, Value
from django.db.models.functions import Coalesce

from .models import DEFAULT_CATEGORIES, Expense, ExpenseCategory

ZERO = Decimal("0.00")
MONEY = DecimalField(max_digits=12, decimal_places=2)


def seed_default_categories():
    """Create the default expense categories for the active business (those
    it doesn't have yet)."""
    for name in DEFAULT_CATEGORIES:
        if not ExpenseCategory.objects.filter(name__iexact=name).exists():
            ExpenseCategory.objects.create(name=name)


def expenses_total(date_from, date_to):
    """Sum of expenses dated date_from..date_to (inclusive)."""
    return Expense.objects.filter(expense_date__gte=date_from, expense_date__lte=date_to).aggregate(
        total=Coalesce(Sum("amount"), Value(ZERO), output_field=MONEY)
    )["total"]


def expenses_summary(date_from, date_to):
    """Total and per-category breakdown, largest first."""
    in_range = Expense.objects.filter(expense_date__gte=date_from, expense_date__lte=date_to)
    by_category = (
        in_range.order_by()
        .values("category", "category__name")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total", "category__name")
    )
    return {
        "date_from": date_from,
        "date_to": date_to,
        "total": expenses_total(date_from, date_to),
        "count": in_range.count(),
        "by_category": [
            {
                "category": row["category"],
                "category_name": row["category__name"],
                "total": row["total"],
                "count": row["count"],
            }
            for row in by_category
        ],
    }
