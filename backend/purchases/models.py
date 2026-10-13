from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from core.models import TenantModel


def _money(**kwargs):
    return models.DecimalField(max_digits=12, decimal_places=2, **kwargs)


class Purchase(TenantModel):
    """FR-14 purchase from a supplier. A DRAFT can be edited and holds no
    stock; receiving it writes PURCHASE stock movements in one transaction
    (purchases.services.receive_purchase). A received purchase is never
    edited or deleted; stock mistakes are corrected with adjustments."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        RECEIVED = "RECEIVED", "Received"
        CANCELLED = "CANCELLED", "Cancelled"

    number = models.PositiveIntegerField(help_text="Purchase number, sequential per business.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    supplier = models.ForeignKey(
        "catalog.Supplier", on_delete=models.PROTECT, null=True, blank=True, related_name="purchases"
    )
    reference = models.CharField(
        max_length=64, blank=True, help_text="The supplier's invoice or delivery note number."
    )
    purchase_date = models.DateField(
        default=timezone.localdate, help_text="When the goods arrive. New batches get this date."
    )
    note = models.CharField(max_length=255, blank=True)
    total = _money(default=0, help_text="Sum of the lines' quantity × unit cost.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="purchases"
    )
    received_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="received_purchases",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cancelled_purchases",
    )
    cancel_reason = models.CharField(max_length=255, blank=True)

    class Meta(TenantModel.Meta):
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["business", "number"], name="purchases_purchase_unique_number_per_business"
            ),
            models.CheckConstraint(condition=Q(total__gte=0), name="purchases_purchase_total_not_negative"),
        ]
        indexes = [
            *TenantModel.Meta.indexes,
            models.Index(fields=["business", "created_at"], name="purchase_biz_created_idx"),
            models.Index(fields=["business", "purchase_date"], name="purchase_biz_date_idx"),
        ]

    def __str__(self):
        return self.purchase_number

    @property
    def purchase_number(self):
        return f"P-{self.number:06d}"

    def save(self, *args, **kwargs):
        self.assign_business()
        self.check_same_business("supplier")
        super().save(*args, **kwargs)


class PurchaseItem(TenantModel):
    """One line of a purchase. `unit_cost` is what was actually paid, kept
    as typed so later cost changes never rewrite it. `batch` is filled in
    when the purchase is received."""

    purchase = models.ForeignKey(Purchase, on_delete=models.PROTECT, related_name="items")
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="purchase_items"
    )
    quantity = models.PositiveIntegerField()
    unit_cost = _money(help_text="Cost per unit paid to the supplier.")
    line_total = _money(help_text="quantity × unit_cost.")
    batch_number = models.CharField(
        max_length=64, blank=True, help_text="Blank for products that don't track expiry."
    )
    expiry_date = models.DateField(null=True, blank=True)
    batch = models.ForeignKey(
        "catalog.ProductBatch",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_items",
    )

    class Meta(TenantModel.Meta):
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["purchase", "product", "batch_number"],
                name="purchases_item_unique_product_batch",
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="purchases_item_quantity_positive"),
            models.CheckConstraint(condition=Q(unit_cost__gte=0), name="purchases_item_cost_not_negative"),
            models.CheckConstraint(
                condition=Q(line_total=F("quantity") * F("unit_cost")), name="purchases_item_line_total"
            ),
        ]

    def __str__(self):
        return f"{self.quantity} × {self.product}"

    def save(self, *args, **kwargs):
        self.assign_business()
        self.check_same_business("purchase", "product", "batch")
        if self.batch is not None and self.batch.product_id != self.product_id:
            raise ValueError("PurchaseItem.batch belongs to a different product.")
        super().save(*args, **kwargs)
