from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from core.models import TenantModel


def _money(**kwargs):
    return models.DecimalField(max_digits=12, decimal_places=2, **kwargs)


class Customer(TenantModel):
    """Someone the business sells to. Required for a sale on credit, so what
    each person still owes can be tracked."""

    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)

    class Meta(TenantModel.Meta):
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["business", "phone"],
                condition=~Q(phone=""),
                name="sales_customer_unique_phone_per_business",
            ),
        ]
        indexes = [
            *TenantModel.Meta.indexes,
            models.Index(fields=["business", "name"], name="customer_biz_name_idx"),
        ]

    def __str__(self):
        return f"{self.name} ({self.phone})" if self.phone else self.name


class Sale(TenantModel):
    """FR-11 sale header. Totals are fixed when the sale is recorded, from the
    items' snapshots. What has been paid and what is still owed are derived
    from the sale's payments (sales.services.with_payment_totals), never
    stored. A sale is never deleted; a mistake is voided."""

    class Status(models.TextChoices):
        COMPLETED = "COMPLETED", "Completed"
        VOID = "VOID", "Void"

    number = models.PositiveIntegerField(help_text="Receipt number, sequential per business.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.COMPLETED)
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, null=True, blank=True, related_name="sales"
    )
    sold_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales"
    )
    subtotal = _money(help_text="Sum of quantity × unit price, before discounts.")
    discount_total = _money(default=0)
    total = _money(help_text="What the customer owes for this sale: subtotal − discounts.")
    cost_total = _money(help_text="COGS: sum of quantity × snapshotted unit cost.")
    note = models.CharField(max_length=255, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="voided_sales",
    )
    void_reason = models.CharField(max_length=255, blank=True)

    class Meta(TenantModel.Meta):
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["business", "number"], name="sales_sale_unique_number_per_business"
            ),
            models.CheckConstraint(
                condition=Q(subtotal__gte=0)
                & Q(discount_total__gte=0)
                & Q(total__gte=0)
                & Q(cost_total__gte=0),
                name="sales_sale_amounts_not_negative",
            ),
            models.CheckConstraint(
                condition=Q(total=F("subtotal") - F("discount_total")),
                name="sales_sale_total_is_subtotal_less_discount",
            ),
        ]
        indexes = [
            *TenantModel.Meta.indexes,
            models.Index(fields=["business", "created_at"], name="sale_biz_created_idx"),
        ]

    def __str__(self):
        return self.receipt_number

    @property
    def receipt_number(self):
        return f"S-{self.number:06d}"

    @property
    def gross_profit(self):
        return self.total - self.cost_total

    def save(self, *args, **kwargs):
        self.assign_business()
        self.check_same_business("customer")
        super().save(*args, **kwargs)


class SaleItem(TenantModel):
    """One line of a sale. Price and cost are copied from the product when the
    sale is recorded, so later price changes never rewrite past profit."""

    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="items")
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="sale_items"
    )
    quantity = models.PositiveIntegerField()
    unit_price = _money(help_text="Product selling price at the time of sale.")
    discount = _money(default=0, help_text="Discount on the whole line, in TZS.")
    line_total = _money(help_text="quantity × unit_price − discount.")
    unit_cost = _money(help_text="Product cost price at the time of sale.")
    line_cost = _money(help_text="quantity × unit_cost.")

    class Meta(TenantModel.Meta):
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="sales_item_quantity_positive"),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0) & Q(unit_cost__gte=0) & Q(discount__gte=0),
                name="sales_item_amounts_not_negative",
            ),
            models.CheckConstraint(
                condition=Q(discount__lte=F("quantity") * F("unit_price")),
                name="sales_item_discount_within_line",
            ),
            models.CheckConstraint(
                condition=Q(line_total=F("quantity") * F("unit_price") - F("discount")),
                name="sales_item_line_total",
            ),
            models.CheckConstraint(
                condition=Q(line_cost=F("quantity") * F("unit_cost")),
                name="sales_item_line_cost",
            ),
        ]

    def __str__(self):
        return f"{self.quantity} × {self.product}"

    def save(self, *args, **kwargs):
        self.assign_business()
        self.check_same_business("sale", "product")
        super().save(*args, **kwargs)


class SaleItemAllocation(TenantModel):
    """How many units of a sale line came from which batch (FEFO), so a void
    returns stock to exactly those batches."""

    sale_item = models.ForeignKey(SaleItem, on_delete=models.PROTECT, related_name="allocations")
    batch = models.ForeignKey(
        "catalog.ProductBatch", on_delete=models.PROTECT, related_name="sale_allocations"
    )
    quantity = models.PositiveIntegerField()

    class Meta(TenantModel.Meta):
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="sales_allocation_quantity_positive"
            ),
        ]

    def save(self, *args, **kwargs):
        self.assign_business()
        self.check_same_business("sale_item", "batch")
        if self.batch.product_id != self.sale_item.product_id:
            raise ValueError("SaleItemAllocation.batch belongs to a different product.")
        super().save(*args, **kwargs)


class PaymentImmutable(RuntimeError):
    """Payments are append-only: never updated or deleted."""


class Payment(TenantModel):
    """Money received for a sale (PAYMENT) or given back when it is voided
    (REFUND). A sale on credit gets more PAYMENT rows as the customer pays
    off the balance. Corrections are new rows, never edits."""

    class Kind(models.TextChoices):
        PAYMENT = "PAYMENT", "Payment"
        REFUND = "REFUND", "Refund"

    class Method(models.TextChoices):
        CASH = "CASH", "Cash"

    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="payments")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PAYMENT)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    amount = _money(help_text="Amount applied to the sale (always positive).")
    amount_received = _money(default=0, help_text="Cash handed over by the customer.")
    change_given = _money(default=0, help_text="Cash given back: amount_received − amount.")
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments"
    )
    note = models.CharField(max_length=255, blank=True)

    class Meta(TenantModel.Meta):
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="sales_payment_amount_positive"),
            models.CheckConstraint(
                condition=Q(amount_received__gte=0) & Q(change_given__gte=0),
                name="sales_payment_cash_not_negative",
            ),
        ]
        indexes = [
            *TenantModel.Meta.indexes,
            models.Index(fields=["business", "created_at"], name="payment_biz_created_idx"),
        ]

    def __str__(self):
        return f"{self.kind} {self.amount} for {self.sale}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PaymentImmutable("Payments cannot be changed; void the sale instead.")
        self.assign_business()
        self.check_same_business("sale")
        super().save(*args, **kwargs)


# pre_delete also covers QuerySet deletes (Django sends it per object).
@receiver(pre_delete, sender=Payment)
def protect_payments(sender, instance, **kwargs):
    raise PaymentImmutable("Payments cannot be deleted; void the sale instead.")
