"""Request-scoped tenant context.

The active business id lives in a ContextVar. It is set only by
TenantJWTAuthentication (from the verified token) or by tenant_context() in
trusted server-side code, never from client-supplied input.
"""

import uuid
from contextlib import contextmanager
from contextvars import ContextVar

TENANT_CLAIM = "business_id"

_current_business_id: ContextVar[uuid.UUID | None] = ContextVar(
    "current_business_id", default=None
)


class TenantContextMissing(RuntimeError):
    """A tenant-scoped query or write ran with no active business."""


class TenantMismatch(RuntimeError):
    """A tenant-owned object belongs to a business other than the active one."""


def get_current_business_id():
    return _current_business_id.get()


def require_current_business_id():
    business_id = _current_business_id.get()
    if business_id is None:
        raise TenantContextMissing(
            "No active business. Use tenant_context(business) or "
            "Model.all_objects for trusted unscoped access."
        )
    return business_id


def set_current_business_id(business_id):
    if business_id is not None and not isinstance(business_id, uuid.UUID):
        business_id = uuid.UUID(str(business_id))
    return _current_business_id.set(business_id)


def reset_current_business_id(token):
    _current_business_id.reset(token)


@contextmanager
def tenant_context(business):
    """Activate `business` (instance or id) for the enclosed block."""
    token = set_current_business_id(getattr(business, "pk", business))
    try:
        yield
    finally:
        reset_current_business_id(token)
