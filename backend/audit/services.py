"""FR-20 audit trail. Call record() inside the same transaction as the
action it describes, so a rollback removes the entry too."""

from django.db import models
from django.db.models.fields.files import FieldFile

from core.actor import get_current_actor

from .models import AuditLog

Action = AuditLog.Action


def _plain(value):
    """A JSON-friendly snapshot of a field value."""
    if isinstance(value, models.Model):
        return str(value)
    if isinstance(value, FieldFile):
        return value.name or None
    return value


def _identity(value):
    """What decides whether a value changed: related rows by pk, since two
    rows can print the same."""
    return value.pk if isinstance(value, models.Model) else _plain(value)


def diff(instance, data):
    """{field: [old, new]} for each field in `data` whose value differs from
    the instance's current one. Call before saving."""
    changes = {}
    for field, new in data.items():
        old = getattr(instance, field, None)
        if _identity(old) != _identity(new):
            changes[field] = [_plain(old), _plain(new)]
    return changes


def record(action, *, target=None, label=None, changes=None, actor=None, ip=None, business=None):
    """Write one audit entry. The actor and IP default to the request's
    (core.actor); the business comes from the tenant context, or from
    `business` in trusted code that runs without one (Django admin).

    Record a delete before deleting: afterwards the target has no pk."""
    current = get_current_actor()
    if actor is None and current is not None:
        actor = current.user
    if ip is None and current is not None:
        ip = current.ip
    entry = AuditLog(
        actor=actor,
        action=action,
        target_type=target._meta.model_name if target is not None else "",
        target_id=target.pk if target is not None else None,
        target_label=(str(target) if label is None and target is not None else label or "")[:255],
        changes=changes or {},
        ip_address=ip,
    )
    if business is not None:
        entry.business = business
    entry.save()
    return entry
