import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from core.tenancy import tenant_context

from .models import (
    Business,
    BusinessSettings,
    PasswordResetToken,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from .rbac import DEFAULT_ROLE_PERMISSIONS


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
        roles = seed_default_roles()
        UserRole.objects.create(user=user, role=roles[Role.OWNER])
        BusinessSettings.objects.create()
    return user, business


def seed_default_roles():
    """Create the system roles for the active business and grant each its
    default permissions (accounts.rbac). Returns {role name: Role}."""
    wanted = set().union(*DEFAULT_ROLE_PERMISSIONS.values())
    catalog = {p.codename: p for p in Permission.objects.filter(codename__in=wanted)}
    missing = wanted - catalog.keys()
    if missing:
        raise RuntimeError(
            f"Permissions missing from the catalog (is a data migration missing?): {sorted(missing)}"
        )

    roles = {}
    for name, codenames in DEFAULT_ROLE_PERMISSIONS.items():
        role = Role.objects.create(name=name, is_system=True)
        for codename in sorted(codenames):
            RolePermission.objects.create(role=role, permission=catalog[codename])
        roles[name] = role
    return roles


def get_permission_codenames(membership):
    """Permission codenames granted to the membership's role, read from
    RolePermission through the tenant-scoped manager (the membership's
    business must be active). Cached on the membership for the request."""
    cached = getattr(membership, "_permission_codenames", None)
    if cached is None:
        cached = frozenset(
            RolePermission.objects.filter(role_id=membership.role_id).values_list(
                "permission__codename", flat=True
            )
        )
        membership._permission_codenames = cached
    return cached


# FR-4 password reset

class InvalidResetToken(Exception):
    """Reset token is unknown, used, expired, or its user is inactive."""


def _hash_reset_token(raw_token):
    return hashlib.sha256(raw_token.encode()).hexdigest()


def request_password_reset(email):
    """Issue a reset token and email it if an active user has this email.
    Does nothing otherwise; callers must respond identically either way."""
    user = User.objects.filter(email__iexact=email, is_active=True).first()
    if user is None:
        return

    raw_token = secrets.token_urlsafe(32)
    now = timezone.now()
    with transaction.atomic():
        PasswordResetToken.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
        PasswordResetToken.objects.create(
            user=user,
            token_hash=_hash_reset_token(raw_token),
            expires_at=now + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT),
        )
        transaction.on_commit(lambda: _send_reset_email(user, raw_token))


def _send_reset_email(user, raw_token):
    # Fragment, not query string: keeps the token out of server logs and Referer.
    link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password#token={raw_token}"
    minutes = settings.PASSWORD_RESET_TIMEOUT // 60
    send_mail(
        subject="Reset your Beauty Business Manager password",
        message=(
            "We received a request to reset your password.\n\n"
            f"Open this link within {minutes} minutes to choose a new one:\n{link}\n\n"
            "If you did not ask for this, you can ignore this email."
        ),
        from_email=None,
        recipient_list=[user.email],
    )


@transaction.atomic
def confirm_password_reset(raw_token, new_password):
    """Set a new password with a valid token, spend every outstanding token
    for the user, and blacklist their refresh tokens (ends all sessions).

    Raises InvalidResetToken, or django ValidationError for a weak password
    (in which case the token stays usable).
    """
    try:
        token = (
            PasswordResetToken.objects.select_for_update()
            .select_related("user")
            .get(token_hash=_hash_reset_token(raw_token))
        )
    except PasswordResetToken.DoesNotExist:
        raise InvalidResetToken
    now = timezone.now()
    if token.used_at is not None or token.expires_at <= now or not token.user.is_active:
        raise InvalidResetToken

    user = token.user
    validate_password(new_password, user=user)
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])

    PasswordResetToken.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token=t) for t in OutstandingToken.objects.filter(user=user)],
        ignore_conflicts=True,
    )
    return user
