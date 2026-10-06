"""Stock ledger operations (FR-7, FR-8) and derived-stock queries.

Every stock change goes through record_movement(). Stock on hand is never
stored: it is computed from StockMovement rows by the annotations below.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import (
    BooleanField,
    Case,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounts.models import BusinessSettings
from catalog.models import Product, ProductBatch

from .models import StockMovement


class InsufficientStock(Exception):
    def __init__(self, available, requested):
        self.available = available
        self.requested = requested
        super().__init__(f"Only {available} in stock; cannot remove {requested}.")


# ---- derived stock -----------------------------------------------------------

def _stock_sum(field):
    """Sum of movement quantities for the outer row (matched on `field`), 0 if none."""
    movements = (
        StockMovement.objects.filter(**{field: OuterRef("pk")})
        .order_by()
        .values(field)
        .annotate(total=Sum("quantity"))
        .values("total")
    )
    return Coalesce(Subquery(movements, output_field=IntegerField()), Value(0))


def with_batch_stock(batches):
    return batches.annotate(stock_on_hand=_stock_sum("batch"))


def with_product_stock(products, threshold=None):
    """Annotate stock_on_hand, threshold, stock_status ('out'|'low'|'in'),
    is_low_stock and nearest_expiry (earliest expiry among batches that still
    hold stock). Low stock includes out of stock.

    Without `threshold`, the business default is read in the same SQL query
    (scoped subquery), so building the queryset runs no query."""
    if threshold is None:
        threshold = Subquery(
            BusinessSettings.objects.values("low_stock_threshold")[:1],
            output_field=IntegerField(),
        )
    else:
        threshold = Value(threshold)
    nearest_expiry = (
        with_batch_stock(
            ProductBatch.objects.filter(product=OuterRef("pk"), expiry_date__isnull=False)
        )
        .filter(stock_on_hand__gt=0)
        .order_by("expiry_date")
        .values("expiry_date")[:1]
    )
    return products.annotate(
        stock_on_hand=_stock_sum("product"),
        threshold=Coalesce("reorder_level", threshold),
        nearest_expiry=Subquery(nearest_expiry),
    ).annotate(
        stock_status=Case(
            When(stock_on_hand__lte=0, then=Value("out")),
            When(stock_on_hand__lte=F("threshold"), then=Value("low")),
            default=Value("in"),
        ),
        is_low_stock=Case(
            When(stock_on_hand__lte=F("threshold"), then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        ),
    )


def expiring_batches(*, within_days=None, expired=False, today=None):
    """Batches of active products that still hold stock and are expired, or
    expire within `within_days` from today (inclusive)."""
    today = today or timezone.localdate()
    batches = with_batch_stock(
        ProductBatch.objects.filter(expiry_date__isnull=False, product__is_active=True)
    ).filter(stock_on_hand__gt=0)
    if expired:
        return batches.filter(expiry_date__lt=today)
    return batches.filter(
        expiry_date__gte=today, expiry_date__lte=today + timedelta(days=within_days)
    )


def inventory_summary(today=None):
    """Counts for the dashboard (FR-17 low-stock/expiry tiles)."""
    business_settings = BusinessSettings.objects.get()
    products = with_product_stock(
        Product.objects.filter(is_active=True), threshold=business_settings.low_stock_threshold
    )
    counts = products.aggregate(
        low_stock=Sum(Case(When(is_low_stock=True, then=1), default=0)),
        out_of_stock=Sum(Case(When(stock_status="out", then=1), default=0)),
    )
    return {
        "low_stock": counts["low_stock"] or 0,
        "out_of_stock": counts["out_of_stock"] or 0,
        "expiring_soon": expiring_batches(
            within_days=business_settings.expiry_warning_days, today=today
        ).count(),
        "expired": expiring_batches(expired=True, today=today).count(),
        "expiry_warning_days": business_settings.expiry_warning_days,
    }


# ---- writes ------------------------------------------------------------------

@transaction.atomic
def record_movement(*, product, batch, movement_type, quantity, user, reason=""):
    """Append one movement. Refuses to take a batch below zero; the per-business
    oversell override arrives with sales in Phase 3 (FR-13)."""
    # Lock the batch so concurrent movements on it are applied one at a time.
    ProductBatch.objects.select_for_update().get(pk=batch.pk)
    if quantity < 0:
        available = with_batch_stock(ProductBatch.objects.filter(pk=batch.pk)).get().stock_on_hand
        if available + quantity < 0:
            raise InsufficientStock(available, -quantity)
    return StockMovement.objects.create(
        product=product,
        batch=batch,
        movement_type=movement_type,
        quantity=quantity,
        reason=reason,
        created_by=user,
    )


def resolve_batch(product, *, batch=None, batch_number="", expiry_date=None, received_on=None):
    """The batch a movement applies to: an existing one, or one found/created
    by number. Products that don't track expiry use a single DEFAULT batch."""
    if batch is not None:
        if batch.product_id != product.pk:
            raise ValidationError({"batch": "This batch belongs to a different product."})
        return batch

    if not batch_number:
        if product.tracks_expiry:
            raise ValidationError({"batch_number": "Choose a batch or enter a new batch number."})
        batch_number = ProductBatch.DEFAULT_NUMBER

    existing = ProductBatch.objects.filter(product=product, batch_number=batch_number).first()
    if existing:
        if expiry_date and existing.expiry_date != expiry_date:
            raise ValidationError(
                {"expiry_date": f"Batch {batch_number} already exists with a different expiry date."}
            )
        return existing

    if product.tracks_expiry and not expiry_date:
        raise ValidationError({"expiry_date": "New batches of this product need an expiry date."})
    return ProductBatch.objects.create(
        product=product,
        batch_number=batch_number,
        expiry_date=expiry_date if product.tracks_expiry else None,
        received_on=received_on or timezone.localdate(),
    )
