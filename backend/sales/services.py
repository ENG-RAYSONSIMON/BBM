"""Sales (FR-11 to FR-13, FR-16, FR-17): recording a cash sale, payments on
credit, voids, and the derived money totals.

Every write runs in one transaction. Stock leaves through
inventory.services.record_movement(); what a sale has been paid and still
owes is always derived from its Payment rows, never stored.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import (
    Case,
    CharField,
    Count,
    DecimalField,
    F,
    Max,
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
from catalog.models import ProductBatch
from inventory.models import StockMovement
from inventory.services import record_movement, with_batch_stock

from .models import Customer, Payment, Sale, SaleItem, SaleItemAllocation

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
MONEY = DecimalField(max_digits=12, decimal_places=2)


def _money(value):
    return Decimal(value).quantize(CENT)


# ---- derived money -------------------------------------------------------------

def _net_paid(**filters):
    """Payments minus refunds over the Payment rows matching `filters`
    (OuterRef allowed), as a subquery; 0 when there are none."""
    net = (
        Payment.objects.filter(**filters)
        .order_by()
        .values(*filters.keys())
        .annotate(
            net=Sum(
                Case(
                    When(kind=Payment.Kind.REFUND, then=-F("amount")),
                    default=F("amount"),
                    output_field=MONEY,
                )
            )
        )
        .values("net")
    )
    return Coalesce(Subquery(net, output_field=MONEY), Value(ZERO), output_field=MONEY)


def with_payment_totals(sales):
    """Annotate amount_paid (payments − refunds), balance (still owed; 0 for a
    void sale) and payment_status: PAID, PARTIAL, UNPAID or VOID."""
    return sales.annotate(amount_paid=_net_paid(sale=OuterRef("pk"))).annotate(
        balance=Case(
            When(status=Sale.Status.VOID, then=Value(ZERO)),
            default=F("total") - F("amount_paid"),
            output_field=MONEY,
        ),
    ).annotate(
        payment_status=Case(
            When(status=Sale.Status.VOID, then=Value("VOID")),
            When(balance__lte=0, then=Value("PAID")),
            When(amount_paid__lte=0, then=Value("UNPAID")),
            default=Value("PARTIAL"),
            output_field=CharField(),
        ),
    )


def with_customer_balance(customers):
    """Annotate total_bought, amount_paid and balance over the customer's
    completed (non-void) sales."""
    bought = (
        Sale.objects.filter(customer=OuterRef("pk"), status=Sale.Status.COMPLETED)
        .order_by()
        .values("customer")
        .annotate(sum=Sum("total"))
        .values("sum")
    )
    return customers.annotate(
        total_bought=Coalesce(Subquery(bought, output_field=MONEY), Value(ZERO), output_field=MONEY),
        amount_paid=_net_paid(sale__customer=OuterRef("pk"), sale__status=Sale.Status.COMPLETED),
    ).annotate(balance=F("total_bought") - F("amount_paid"))


def sales_summary(date_from, date_to):
    """FR-16/FR-17 figures for local dates date_from..date_to (inclusive).
    Void sales are left out. Profit counts when the sale happens, even on
    credit; cash_collected is what actually came in (payments − refunds) in
    the range, and outstanding_credit is everything still owed, all time."""
    in_range = {"created_at__date__gte": date_from, "created_at__date__lte": date_to}
    totals = Sale.objects.filter(status=Sale.Status.COMPLETED, **in_range).aggregate(
        sales_count=Count("id"),
        revenue=Coalesce(Sum("total"), Value(ZERO), output_field=MONEY),
        discounts=Coalesce(Sum("discount_total"), Value(ZERO), output_field=MONEY),
        cogs=Coalesce(Sum("cost_total"), Value(ZERO), output_field=MONEY),
    )

    def net(payments):
        return payments.aggregate(
            net=Coalesce(
                Sum(
                    Case(
                        When(kind=Payment.Kind.REFUND, then=-F("amount")),
                        default=F("amount"),
                        output_field=MONEY,
                    )
                ),
                Value(ZERO),
                output_field=MONEY,
            )
        )["net"]

    owed_total = Sale.objects.filter(status=Sale.Status.COMPLETED).aggregate(
        sum=Coalesce(Sum("total"), Value(ZERO), output_field=MONEY)
    )["sum"]
    owed_paid = net(Payment.objects.filter(sale__status=Sale.Status.COMPLETED))
    return {
        "date_from": date_from,
        "date_to": date_to,
        **totals,
        "gross_profit": totals["revenue"] - totals["cogs"],
        "cash_collected": net(Payment.objects.filter(**in_range)),
        "outstanding_credit": owed_total - owed_paid,
    }


# ---- writes --------------------------------------------------------------------

def _sellable_batches(product, today):
    """FEFO order: earliest expiry first (no expiry last), then oldest
    received. Expired batches are never sold."""
    return (
        with_batch_stock(ProductBatch.objects.filter(product=product))
        .filter(stock_on_hand__gt=0)
        .filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=today))
        .order_by(F("expiry_date").asc(nulls_last=True), F("received_on").asc(nulls_last=True), "created_at")
    )


def _price_lines(lines):
    """Validate the requested lines and compute their snapshot amounts."""
    if not lines:
        raise ValidationError({"items": ["Add at least one product to the sale."]})
    seen = set()
    priced = []
    for index, line in enumerate(lines):
        product, quantity = line["product"], line["quantity"]
        discount = _money(line.get("discount") or 0)
        if product.pk in seen:
            raise ValidationError({"items": [f"{product.name} is listed twice. Use one line per product."]})
        seen.add(product.pk)
        if not product.is_active:
            raise ValidationError({"items": [f"{product.name} is archived and can't be sold."]})
        if quantity <= 0:
            raise ValidationError({"items": [f"{product.name}: quantity must be at least 1."]})
        unit_price = _money(product.selling_price)
        unit_cost = _money(product.cost_price)
        gross = unit_price * quantity
        if discount < 0 or discount > gross:
            raise ValidationError(
                {"items": [f"{product.name}: the discount must be between 0 and {gross:,.2f}."]}
            )
        priced.append(
            {
                "product": product,
                "quantity": quantity,
                "unit_price": unit_price,
                "discount": discount,
                "line_total": gross - discount,
                "unit_cost": unit_cost,
                "line_cost": unit_cost * quantity,
            }
        )
    return priced


@transaction.atomic
def create_sale(*, user, lines, customer=None, new_customer=None, amount_received=ZERO, note=""):
    """FR-11/FR-12: record a sale in one transaction. Any failure rolls back
    every row and stock movement written here.

    `lines` are dicts with product, quantity and optional discount (TZS for
    the whole line). `amount_received` is the cash handed over: anything
    above the total is change, anything short stays owed, which needs a
    customer (an existing one, or `new_customer` {name, phone})."""
    amount_received = _money(amount_received)
    if amount_received < 0:
        raise ValidationError({"amount_received": ["Enter the cash received (0 or more)."]})
    priced = _price_lines(lines)
    subtotal = sum((line["unit_price"] * line["quantity"] for line in priced), ZERO)
    discount_total = sum((line["discount"] for line in priced), ZERO)
    total = subtotal - discount_total
    paid = min(amount_received, total)

    if paid < total and customer is None and not new_customer:
        raise ValidationError(
            {"customer": ["The cash received is less than the total. Choose the customer who owes the rest."]}
        )

    # Serialises receipt numbers per business: the settings row is the lock.
    BusinessSettings.objects.select_for_update().get()
    number = (Sale.objects.aggregate(last=Max("number"))["last"] or 0) + 1

    # Lock every batch of the products being sold, in a fixed order so two
    # concurrent sales can't deadlock, then check sellable stock.
    products = sorted((line["product"] for line in priced), key=lambda product: str(product.pk))
    list(ProductBatch.objects.select_for_update().filter(product__in=products).order_by("pk"))
    today = timezone.localdate()
    shortages = []
    for line in priced:
        batches = list(_sellable_batches(line["product"], today))
        line["batches"] = batches
        available = sum(batch.stock_on_hand for batch in batches)
        if line["quantity"] > available:
            shortages.append(f"{line['product'].name}: only {available} available to sell.")
    if shortages:
        raise ValidationError({"items": shortages})

    if customer is None and new_customer:
        customer = Customer.objects.create(
            name=new_customer["name"].strip(), phone=new_customer.get("phone", "").strip()
        )

    sale = Sale.objects.create(
        number=number,
        customer=customer,
        sold_by=user,
        subtotal=subtotal,
        discount_total=discount_total,
        total=total,
        cost_total=sum((line["line_cost"] for line in priced), ZERO),
        note=note,
    )
    reason = f"Sale {sale.receipt_number}"
    for line in priced:
        item = SaleItem.objects.create(
            sale=sale,
            product=line["product"],
            quantity=line["quantity"],
            unit_price=line["unit_price"],
            discount=line["discount"],
            line_total=line["line_total"],
            unit_cost=line["unit_cost"],
            line_cost=line["line_cost"],
        )
        remaining = line["quantity"]
        for batch in line["batches"]:
            if remaining == 0:
                break
            take = min(remaining, batch.stock_on_hand)
            record_movement(
                product=line["product"],
                batch=batch,
                movement_type=StockMovement.Type.SALE,
                quantity=-take,
                user=user,
                reason=reason,
            )
            SaleItemAllocation.objects.create(sale_item=item, batch=batch, quantity=take)
            remaining -= take

    if paid > 0:
        Payment.objects.create(
            sale=sale,
            amount=paid,
            amount_received=amount_received,
            change_given=amount_received - paid,
            received_by=user,
        )
    return sale


def _locked_with_totals(sale):
    Sale.objects.select_for_update().filter(pk=sale.pk).get()
    return with_payment_totals(Sale.objects.filter(pk=sale.pk)).get()


@transaction.atomic
def record_payment(*, sale, user, amount_received, note=""):
    """Cash paid towards what a sale still owes. Anything above the balance
    is given back as change."""
    amount_received = _money(amount_received)
    sale = _locked_with_totals(sale)
    if sale.status == Sale.Status.VOID:
        raise ValidationError("This sale is void.")
    if sale.balance <= 0:
        raise ValidationError("Nothing is owed on this sale.")
    if amount_received <= 0:
        raise ValidationError({"amount_received": ["Enter the cash received."]})
    amount = min(amount_received, sale.balance)
    return Payment.objects.create(
        sale=sale,
        amount=amount,
        amount_received=amount_received,
        change_given=amount_received - amount,
        received_by=user,
        note=note,
    )


@transaction.atomic
def void_sale(*, sale, user, reason):
    """Cancel a sale: its stock goes back to the batches it came from (RETURN
    movements), the cash collected is refunded, and the sale stays on record
    as VOID. Nothing is deleted."""
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": ["Say why the sale is being voided."]})
    sale = _locked_with_totals(sale)
    if sale.status == Sale.Status.VOID:
        raise ValidationError("This sale is already void.")

    movement_reason = f"Void of {sale.receipt_number}: {reason}"[:255]
    allocations = SaleItemAllocation.objects.filter(sale_item__sale=sale).select_related(
        "sale_item__product", "batch"
    )
    for allocation in allocations:
        record_movement(
            product=allocation.sale_item.product,
            batch=allocation.batch,
            movement_type=StockMovement.Type.RETURN,
            quantity=allocation.quantity,
            user=user,
            reason=movement_reason,
        )
    if sale.amount_paid > 0:
        Payment.objects.create(
            sale=sale,
            kind=Payment.Kind.REFUND,
            amount=sale.amount_paid,
            received_by=user,
            note=reason[:255],
        )
    sale.status = Sale.Status.VOID
    sale.voided_at = timezone.now()
    sale.voided_by = user
    sale.void_reason = reason[:255]
    sale.save(update_fields=["status", "voided_at", "voided_by", "void_reason", "updated_at"])
    return sale
