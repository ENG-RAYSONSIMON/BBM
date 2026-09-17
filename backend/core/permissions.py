from django.core.exceptions import ImproperlyConfigured
from rest_framework.permissions import BasePermission

from accounts.services import get_permission_codenames


class HasTenantPermission(BasePermission):
    """FR-5: allow a request only if the caller's role in the token's business
    holds every permission the view requires.

    Views declare `required_permissions` as a tuple of codenames (all methods)
    or a dict of HTTP method -> tuple. Undeclared views raise
    ImproperlyConfigured; methods missing from a dict are denied. The role comes
    from request.membership, set by TenantJWTAuthentication from the signed
    token, and grants are read from RolePermission rows, never role names.
    """

    def has_permission(self, request, view):
        required = getattr(view, "required_permissions", None)
        if required is None:
            raise ImproperlyConfigured(
                f"{type(view).__name__} must declare required_permissions "
                "(use () if any member of the business may call it)."
            )
        if isinstance(required, dict):
            method = "GET" if request.method == "HEAD" else request.method
            required = required.get(method)
            if required is None:
                return False

        membership = getattr(request, "membership", None)
        if membership is None:
            return False
        return set(required) <= get_permission_codenames(membership)
