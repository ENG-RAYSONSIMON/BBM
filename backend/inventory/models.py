from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from core.models import TenantModel


class LedgerImmutable(RuntimeError):
    """Stock movements are append-only: never updated or deleted."""


class StockMovement(TenantModel):
    """FR-7: one row per stock change. Stock on hand for a batch or product is
    the sum of `quantity` over its rows (FR-8); nothing else stores stock.

    Corrections are new rows (an ADJUSTMENT), never edits.
    """

    class Type(models.TextChoices):
        PURCHASE = "PURCHASE", "Purchase"
        SALE = "SALE", "Sale"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"
        DAMAGE = "DAMAGE", "Damage"
        EXPIRY = "EXPIRY", "Expiry"
        TRANSFER = "TRANSFER", "Transfer"
        RETURN = "RETURN", "Return"

    # Types whose quantity must be negative / positive. ADJUSTMENT and
    # TRANSFER may go either way.
    OUTBOUND = (Type.SALE, Type.DAMAGE, Type.EXPIRY)
    INBOUND = (Type.PURCHASE, Type.RETURN)

    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="stock_movements"
    )
    batch = models.ForeignKey(
        "catalog.ProductBatch", on_delete=models.PROTECT, related_name="stock_movements"
    )
    movement_type = models.CharField(max_length=20, choices=Type.choices)
    quantity = models.IntegerField(help_text="Signed: positive adds stock, negative removes it.")
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stock_movements"
    )

    class Meta(TenantModel.Meta):
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=~Q(quantity=0), name="inventory_movement_quantity_not_zero"
            ),
            models.CheckConstraint(
                condition=~Q(movement_type__in=["SALE", "DAMAGE", "EXPIRY"]) | Q(quantity__lt=0),
                name="inventory_movement_outbound_is_negative",
            ),
            models.CheckConstraint(
                condition=~Q(movement_type="PURCHASE") | Q(quantity__gt=0),
                name="inventory_movement_purchase_is_positive",
            ),
            # Stock coming back from a voided sale.
            models.CheckConstraint(
                condition=~Q(movement_type="RETURN") | Q(quantity__gt=0),
                name="inventory_movement_return_is_positive",
            ),
        ]
        indexes = [
            *TenantModel.Meta.indexes,
            models.Index(fields=["business", "created_at"], name="movement_biz_created_idx"),
            models.Index(fields=["business", "product", "batch"], name="movement_biz_prod_batch_idx"),
        ]

    def __str__(self):
        return f"{self.movement_type} {self.quantity:+d} {self.product}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise LedgerImmutable("Stock movements cannot be changed; record a new adjustment.")
        self.assign_business()
        self.check_same_business("product", "batch")
        if self.batch.product_id != self.product_id:
            raise ValueError("StockMovement.batch belongs to a different product.")
        super().save(*args, **kwargs)


# pre_delete also covers QuerySet deletes (Django sends it per object).
@receiver(pre_delete, sender=StockMovement)
def protect_ledger(sender, instance, **kwargs):
    raise LedgerImmutable("Stock movements cannot be deleted; record a new adjustment.")
