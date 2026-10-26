"""Purchases (FR-14): drafts, receiving stock, cancelling.

A draft holds no stock. receive_purchase() writes every PURCHASE movement
through inventory.services.record_movement() inside one transaction, so a
failure on any line leaves nothing behind. Receiving also sets each
product's cost_price to what was just paid, so later sales snapshot the
latest cost; past sales keep their own snapshots.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext as _

from accounts.models import BusinessSettings
from audit.services import Action, record
from catalog.models import ProductBatch
from inventory.models import StockMovement
from inventory.services import record_movement, resolve_batch

from .models import Purchase, PurchaseItem

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def _money(value):
    return Decimal(value).quantize(CENT)


def _check_lines(lines):
    """Validate the requested lines (without writing) and compute their
    totals. Batch rules match inventory.services.resolve_batch(), which runs
    again on receive."""
    if not lines:
        raise ValidationError({"items": [_("Add at least one product to the purchase.")]})
    seen = set()
    checked = []
    for line in lines:
        product, quantity = line["product"], line["quantity"]
        unit_cost = _money(line["unit_cost"])
        batch_number = (line.get("batch_number") or "").strip()
        expiry_date = line.get("expiry_date")
        name = product.name

        if not product.is_active:
            raise ValidationError({"items": [_("%(name)s is archived. Reactivate it before buying more.") % {"name": name}]})
        if quantity <= 0:
            raise ValidationError({"items": [_("%(name)s: quantity must be at least 1.") % {"name": name}]})
        if unit_cost < 0:
            raise ValidationError({"items": [_("%(name)s: the unit cost can't be negative.") % {"name": name}]})

        if product.tracks_expiry:
            if not batch_number:
                raise ValidationError(
                    {"items": [_("%(name)s: enter the batch number printed on the stock.") % {"name": name}]}
                )
            existing = ProductBatch.objects.filter(product=product, batch_number=batch_number).first()
            if existing is None and not expiry_date:
                raise ValidationError(
                    {
                        "items": [
                            _("%(name)s: batch %(batch)s is new and needs an expiry date.")
                            % {"name": name, "batch": batch_number}
                        ]
                    }
                )
            if existing is not None and expiry_date and existing.expiry_date != expiry_date:
                raise ValidationError(
                    {
                        "items": [
                            _("%(name)s: batch %(batch)s already exists with a different expiry date.")
                            % {"name": name, "batch": batch_number}
                        ]
                    }
                )
        else:
            # A single DEFAULT batch holds stock for products without expiry.
            batch_number, expiry_date = "", None

        key = (product.pk, batch_number.lower())
        if key in seen:
            raise ValidationError(
                {"items": [_("%(name)s is listed twice for the same batch. Use one line.") % {"name": name}]}
            )
        seen.add(key)
        checked.append(
            {
                "product": product,
                "quantity": quantity,
                "unit_cost": unit_cost,
                "line_total": unit_cost * quantity,
                "batch_number": batch_number,
                "expiry_date": expiry_date,
            }
        )
    return checked


@transaction.atomic
def save_draft(*, user, lines, purchase=None, supplier=None, reference="", purchase_date=None, note=""):
    """Create a draft purchase, or replace an existing draft's details and
    lines. Nothing touches stock until the purchase is received."""
    checked = _check_lines(lines)
    if purchase is None:
        # Serialises purchase numbers per business: the settings row is the lock.
        BusinessSettings.objects.select_for_update().get()
        number = (Purchase.objects.aggregate(last=Max("number"))["last"] or 0) + 1
        purchase = Purchase(number=number, created_by=user)
    else:
        purchase = Purchase.objects.select_for_update().get(pk=purchase.pk)
        if purchase.status != Purchase.Status.DRAFT:
            raise ValidationError(_("Only a draft purchase can be edited."))
        purchase.items.all().delete()

    purchase.supplier = supplier
    purchase.reference = reference.strip()
    purchase.purchase_date = purchase_date or timezone.localdate()
    purchase.note = note
    purchase.total = sum((line["line_total"] for line in checked), ZERO)
    purchase.save()
    for line in checked:
        PurchaseItem.objects.create(purchase=purchase, **line)
    return purchase


@transaction.atomic
def receive_purchase(*, purchase, user):
    """FR-14: put the purchase's stock on the shelf. Every line's batch,
    PURCHASE movement and cost update is written in this one transaction."""
    purchase = Purchase.objects.select_for_update().get(pk=purchase.pk)
    if purchase.status != Purchase.Status.DRAFT:
        raise ValidationError(
            _("This purchase is already received.")
            if purchase.status == Purchase.Status.RECEIVED
            else _("This purchase is already cancelled.")
        )
    items = list(purchase.items.select_related("product").order_by("created_at"))
    if not items:
        raise ValidationError(_("Add at least one product before receiving."))

    # A product may have been archived or changed its expiry tracking since
    # the draft was saved: re-check the lines against it as it is now.
    checked = _check_lines(
        [
            {
                "product": item.product,
                "quantity": item.quantity,
                "unit_cost": item.unit_cost,
                "batch_number": item.batch_number,
                "expiry_date": item.expiry_date,
            }
            for item in items
        ]
    )

    reason = f"Purchase {purchase.purchase_number}"
    if purchase.reference:
        reason = f"{reason} ({purchase.reference})"
    for item, line in zip(items, checked):
        product = item.product
        batch = resolve_batch(
            product,
            batch_number=line["batch_number"],
            expiry_date=line["expiry_date"],
            received_on=purchase.purchase_date,
        )
        record_movement(
            product=product,
            batch=batch,
            movement_type=StockMovement.Type.PURCHASE,
            quantity=item.quantity,
            user=user,
            reason=reason[:255],
        )
        item.batch = batch
        item.save(update_fields=["batch", "updated_at"])
        # Latest cost wins: future sales snapshot what was last paid.
        product.cost_price = item.unit_cost
        product.save(update_fields=["cost_price", "updated_at"])

    purchase.status = Purchase.Status.RECEIVED
    purchase.received_at = timezone.now()
    purchase.received_by = user
    purchase.save(update_fields=["status", "received_at", "received_by", "updated_at"])
    return purchase


@transaction.atomic
def cancel_purchase(*, purchase, user, reason):
    """Cancel a draft. It stays on record; received purchases can't be
    cancelled (correct their stock with an adjustment)."""
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": [_("Say why the purchase is being cancelled.")]})
    purchase = Purchase.objects.select_for_update().get(pk=purchase.pk)
    if purchase.status != Purchase.Status.DRAFT:
        raise ValidationError(_("Only a draft purchase can be cancelled."))
    purchase.status = Purchase.Status.CANCELLED
    purchase.cancelled_at = timezone.now()
    purchase.cancelled_by = user
    purchase.cancel_reason = reason[:255]
    purchase.save(update_fields=["status", "cancelled_at", "cancelled_by", "cancel_reason", "updated_at"])
    record(Action.PURCHASE_CANCEL, target=purchase, actor=user, changes={"reason": purchase.cancel_reason})
    return purchase
