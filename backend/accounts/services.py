from django.core.exceptions import ValidationError
from django.db import transaction

from core.tenancy import tenant_context

from .models import Business, BusinessSettings, Role, User, UserRole


def get_active_membership(user_id, business_id):
    """Return the active UserRole linking the user to the business, or None.

    Deliberately unscoped: it runs before any business is active, and its
    result is what decides which business becomes active.
    """
    if not user_id or not business_id:
        return None
    try:
        return UserRole.all_objects.select_related("business", "role").get(
            user_id=user_id,
            business_id=business_id,
            is_active=True,
            user__is_active=True,
            business__is_active=True,
        )
    except (UserRole.DoesNotExist, ValidationError, ValueError):
        return None


def get_active_memberships(user):
    return list(
        UserRole.all_objects.select_related("business", "role")
        .filter(user=user, is_active=True, business__is_active=True)
        .order_by("business__name")
    )


@transaction.atomic
def register_owner(*, email, password, business_name, first_name="", last_name="", phone=""):
    """FR-1: create the user, their business, its Owner role, the owner's
    membership and default settings, all or nothing."""
    user = User.objects.create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
    )
    business = Business.objects.create(name=business_name)
    with tenant_context(business):
        owner_role = Role.objects.create(name=Role.OWNER, is_system=True)
        UserRole.objects.create(user=user, role=owner_role)
        BusinessSettings.objects.create()
    return user, business
