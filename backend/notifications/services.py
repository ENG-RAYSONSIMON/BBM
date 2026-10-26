"""FR-19 notification centre: which notifications a user sees, read state,
and the stock alerts made by `manage.py generate_notifications`."""

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from accounts.models import BusinessSettings
from accounts.rbac import INVENTORY_VIEW
from catalog.models import Product
from core.tenancy import require_current_business_id
from inventory.services import expiring_batches, with_product_stock

from .models import Notification, NotificationRead

Kind = Notification.Kind
STOCK_KINDS = (Kind.LOW_STOCK, Kind.EXPIRING, Kind.EXPIRED)


# ---- reading -------------------------------------------------------------------

def visible_to(user, codenames):
    """Notifications of the active business addressed to `user` or to
    everyone, whose required permission the user holds, annotated with
    is_read for that user."""
    return (
        Notification.objects.filter(Q(recipient__isnull=True) | Q(recipient=user))
        .filter(Q(required_permission="") | Q(required_permission__in=codenames))
        .annotate(is_read=Exists(NotificationRead.objects.filter(notification=OuterRef("pk"), user=user)))
    )


def unread(notifications):
    """Open notifications not yet read. Resolved ones need no attention."""
    return notifications.filter(is_read=False, resolved_at__isnull=True)


def mark_read(notification, user):
    NotificationRead.objects.get_or_create(notification=notification, user=user)


def mark_all_read(notifications, user):
    """Mark every notification in the queryset read for the user."""
    business_id = require_current_business_id()
    ids = notifications.filter(is_read=False).values_list("pk", flat=True)
    # bulk_create skips TenantModel.save(): the business is set explicitly.
    NotificationRead.objects.bulk_create(
        [NotificationRead(business_id=business_id, notification_id=pk, user=user) for pk in ids],
        ignore_conflicts=True,
    )


# ---- generating ----------------------------------------------------------------

def _batch_params(batch, today):
    return {
        "product": batch.product_id,
        "name": batch.product.name,
        "batch_number": batch.batch_number,
        "expiry_date": batch.expiry_date,
        "days": abs((batch.expiry_date - today).days),
        "stock": batch.stock_on_hand,
    }


def _wanted_stock_alerts(today):
    """{dedupe_key: (kind, product id, params)} for every stock condition
    that should have an open notification right now."""
    shop = BusinessSettings.objects.get()
    wanted = {}
    low = with_product_stock(Product.objects.filter(is_active=True), threshold=shop.low_stock_threshold)
    for product in low.filter(is_low_stock=True):
        params = {
            "product": product.pk,
            "name": product.name,
            "stock": product.stock_on_hand,
            "threshold": product.threshold,
            "unit": product.unit,
        }
        wanted[f"{Kind.LOW_STOCK}:{product.pk}"] = (Kind.LOW_STOCK, product.pk, params)
    expiring = expiring_batches(within_days=shop.expiry_warning_days, today=today)
    for batch in expiring.select_related("product"):
        wanted[f"{Kind.EXPIRING}:{batch.pk}"] = (Kind.EXPIRING, batch.product_id, _batch_params(batch, today))
    for batch in expiring_batches(expired=True, today=today).select_related("product"):
        wanted[f"{Kind.EXPIRED}:{batch.pk}"] = (Kind.EXPIRED, batch.product_id, _batch_params(batch, today))
    return wanted


def _as_stored(params):
    """Params as they read back from the JSON column (ids and dates as strings)."""
    return json.loads(json.dumps(params, cls=DjangoJSONEncoder))


@transaction.atomic
def sync_stock_notifications(today=None):
    """Bring the active business's stock alerts up to date: open one for
    each new low-stock product and expiring or expired batch, refresh the
    figures (stock, days left) of those still open, and resolve open ones
    whose condition has ended. Safe to run any number of times."""
    today = today or timezone.localdate()
    wanted = _wanted_stock_alerts(today)
    still_open = Notification.objects.filter(kind__in=STOCK_KINDS, resolved_at__isnull=True)
    open_keys = set(still_open.values_list("dedupe_key", flat=True))
    ended = open_keys - set(wanted)
    resolved = still_open.filter(dedupe_key__in=ended).update(resolved_at=timezone.now())

    changed, now = [], timezone.now()
    for notification in still_open.filter(dedupe_key__in=open_keys & set(wanted)):
        params = _as_stored(wanted[notification.dedupe_key][2])
        if notification.params != params:
            notification.params, notification.updated_at = params, now  # bulk_update skips auto_now
            changed.append(notification)
    Notification.objects.bulk_update(changed, ["params", "updated_at"])

    business_id = require_current_business_id()
    new = [
        Notification(
            business_id=business_id,  # bulk_create skips TenantModel.save()
            kind=kind,
            required_permission=INVENTORY_VIEW,
            params=params,
            target_type="product",
            target_id=product_id,
            dedupe_key=key,
        )
        for key, (kind, product_id, params) in wanted.items()
        if key not in open_keys
    ]
    # A concurrent run may have opened the same key: the partial unique
    # constraint makes the second insert a no-op, so count what's really open.
    Notification.objects.bulk_create(new, ignore_conflicts=True)
    opened = still_open.count() - (len(open_keys) - resolved)
    return {"opened": opened, "resolved": resolved, "updated": len(changed)}
