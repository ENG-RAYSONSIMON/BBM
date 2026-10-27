import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils import translation
from django.utils.translation import gettext as _
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from audit.services import Action, record
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

logger = logging.getLogger(__name__)


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
        # Imported here: accounts loads before the apps that depend on it.
        from expenses.services import seed_default_categories

        seed_default_categories()
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
        # In the language the request came in (the app sends Accept-Language).
        language = translation.get_language()
        transaction.on_commit(lambda: _send_reset_email(user, raw_token, language))


def _send_reset_email(user, raw_token, language):
    """Send the reset link. A mail failure is logged, never raised: the
    response must stay the same 202 whether or not the account exists, and
    the token stays valid, so the person can simply ask again."""
    # Fragment, not query string: keeps the token out of server logs and Referer.
    link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password#token={raw_token}"
    minutes = settings.PASSWORD_RESET_TIMEOUT // 60
    with translation.override(language):
        subject = _("Reset your Beauty Business Manager password")
        message = _(
            "We received a request to reset your password.\n\n"
            "Open this link within %(minutes)s minutes to choose a new one:\n%(link)s\n\n"
            "If you did not ask for this, you can ignore this email."
        ) % {"minutes": minutes, "link": link}
    try:
        send_mail(subject=subject, message=message, from_email=None, recipient_list=[user.email])
    except Exception as exc:
        # Only the error type, not its text or traceback: SMTP errors can carry
        # the recipient's address. The user id is enough to look into it.
        logger.error("Password reset email failed for user %s (%s).", user.pk, type(exc).__name__)


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
    _set_password(user, new_password, must_change=False)
    PasswordResetToken.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
    end_sessions(user)
    return user


def _set_password(user, password, *, must_change):
    user.set_password(password)
    user.must_change_password = must_change
    user.save(update_fields=["password", "must_change_password", "updated_at"])


def end_sessions(user):
    """Blacklist every refresh token the user holds, logging them out
    everywhere once their short-lived access token expires."""
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token=t) for t in OutstandingToken.objects.filter(user=user)],
        ignore_conflicts=True,
    )


@transaction.atomic
def change_own_password(user, current_password, new_password):
    """The user chooses a new password (also after a temporary one). Ends
    their other sessions; the caller issues fresh tokens.

    Raises django ValidationError keyed by field."""
    if not user.check_password(current_password):
        raise ValidationError({"current_password": [_("Your current password is wrong.")]})
    try:
        validate_password(new_password, user=user)
    except ValidationError as exc:
        raise ValidationError({"new_password": exc.messages})
    if user.check_password(new_password):
        raise ValidationError({"new_password": [_("Choose a password different from the current one.")]})
    _set_password(user, new_password, must_change=False)
    end_sessions(user)


# Staff management. Run with the business active (tenant_context or the
# request's token); the actor is the caller's own membership.

def role_codenames(role):
    return frozenset(
        RolePermission.objects.filter(role=role).values_list("permission__codename", flat=True)
    )


def can_assign(role, actor_codenames):
    """A role can be given only if it has fewer powers than the giver's:
    every permission it holds, the giver holds too, and the giver holds more.
    So an Admin can add Sellers and Cashiers but not other Admins, and since
    the Owner role holds every permission, nobody can give it."""
    return role_codenames(role) < actor_codenames


def can_manage(membership, actor):
    """Whether `actor` (a membership) may change `membership`: not their own,
    and only someone whose role has fewer powers than the actor's (never the
    Owner)."""
    return (
        membership.user_id != actor.user_id
        and can_assign(membership.role, get_permission_codenames(actor))
    )


def assignable_role_ids(actor):
    """Ids of the active business's roles the actor may give."""
    actor_codenames = get_permission_codenames(actor)
    return {role.pk for role in Role.objects.all() if can_assign(role, actor_codenames)}


def _check_role(role, actor):
    if not can_assign(role, get_permission_codenames(actor)):
        raise ValidationError({"role": [_("You can't give this role.")]})


def _check_manageable(membership, actor):
    # Platform operators are managed in Django admin, never by a shop.
    if membership.user.is_staff or membership.user.is_superuser:
        raise ValidationError({"non_field_errors": [_("This account can't be changed here.")]})
    if membership.user_id == actor.user_id:
        raise ValidationError({"non_field_errors": [_("You can't change your own access.")]})
    if not can_manage(membership, actor):
        raise ValidationError(
            {"non_field_errors": [_("You can't change this person: their role is not below yours.")]}
        )


def _check_not_shared(membership, message):
    """Refuse changes to an account that also belongs to another business:
    this shop must not change or take over a login used elsewhere."""
    # all_objects: the check must see the user's other businesses, which the
    # scoped manager hides. Only existence is read.
    if UserRole.all_objects.filter(user=membership.user).exclude(business_id=membership.business_id).exists():
        raise ValidationError({"non_field_errors": [message]})


def _validate_temp_password(password, user):
    if not password:
        raise ValidationError({"temp_password": [_("Enter a temporary password.")]})
    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        raise ValidationError({"temp_password": exc.messages})


def _staff_label(user):
    return user.get_full_name() or user.email


@transaction.atomic
def add_staff(*, actor, email, role, temp_password, first_name="", last_name="", phone=""):
    """Add a person to the active business with a new account and a
    temporary password, to be changed at first login.

    An email that already has an account is refused: without email
    verification nothing proves the account belongs to this person, and
    whoever made it (e.g. another shop, with a temporary password it knows)
    could then log in here."""
    _check_role(role, actor)
    email = User.objects.normalize_email(email)
    duplicate = ValidationError({"email": [_("This email already has an account. Use a different email.")]})
    if User.objects.filter(email__iexact=email).exists():
        raise duplicate
    user = User(email=email, first_name=first_name, last_name=last_name, phone=phone)
    _validate_temp_password(temp_password, user)
    user.set_password(temp_password)
    user.must_change_password = True
    try:
        with transaction.atomic():
            user.save()
    except IntegrityError:
        # Lost a race with another add or registration for the same email.
        raise duplicate

    membership = UserRole.objects.create(user=user, role=role)
    record(
        Action.STAFF_ADD,
        target=membership,
        label=_staff_label(user),
        changes={"email": user.email, "role": role.name},
    )
    return membership


@transaction.atomic
def change_staff(membership, *, actor, role=None, is_active=None, **details):
    """Change a staff member's role, name or phone, or turn their access off
    or on. Turning off takes effect on their next request (authentication
    checks the membership every time); their sales stay on record. Name and
    phone (`details`) are refused for an account also used at another
    business."""
    membership = UserRole.objects.select_for_update().select_related("role", "user").get(pk=membership.pk)
    _check_manageable(membership, actor)
    user = membership.user
    changes = {
        field: [getattr(user, field), value] for field, value in details.items() if value != getattr(user, field)
    }
    if changes:
        _check_not_shared(
            membership,
            _("This person also uses their account at another business, so their name and phone can't be changed here."),
        )
        for field, (_old, new) in changes.items():
            setattr(user, field, new)
        user.save(update_fields=list(changes))
    if role is not None and role.pk != membership.role_id:
        _check_role(role, actor)
        changes["role"] = [membership.role.name, role.name]
        membership.role = role
    if is_active is not None and is_active != membership.is_active:
        changes["is_active"] = [membership.is_active, is_active]
        membership.is_active = is_active
    if "role" in changes or "is_active" in changes:
        membership.save()
    if changes:
        record(Action.STAFF_CHANGE, target=membership, label=_staff_label(membership.user), changes=changes)
    return membership


@transaction.atomic
def reset_staff_password(membership, *, actor, temp_password):
    """Give a staff member a new temporary password and log them out
    everywhere. Refused for an account that also belongs to another business:
    this shop must not be able to take over a login used elsewhere."""
    membership = UserRole.objects.select_related("role", "user").get(pk=membership.pk)
    _check_manageable(membership, actor)
    user = membership.user
    _check_not_shared(
        membership,
        _("This person also uses their account at another business. Ask them to use “Forgot password” instead."),
    )
    _validate_temp_password(temp_password, user)
    _set_password(user, temp_password, must_change=True)
    end_sessions(user)
    record(Action.STAFF_PASSWORD_RESET, target=membership, label=_staff_label(user))
    return membership
