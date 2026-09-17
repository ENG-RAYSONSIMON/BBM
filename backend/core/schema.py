"""OpenAPI (drf-spectacular) integration for the tenancy and permission layers.

Imported from CoreConfig.ready() so the authentication extension registers.
"""

from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from drf_spectacular.openapi import AutoSchema


class TenantJWTScheme(SimpleJWTScheme):
    target_class = "core.authentication.TenantJWTAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        definition = super().get_security_definition(auto_schema)
        definition["description"] = (
            "Access token from login, register or refresh. Its signed "
            "`business_id` claim selects the business (tenant) for the request."
        )
        return definition


def required_permissions_for(view, method):
    """The codenames a view requires for `method`, or None if it declares
    none. Mirrors core.permissions.HasTenantPermission."""
    required = getattr(view, "required_permissions", None)
    if isinstance(required, dict):
        required = required.get("GET" if method == "HEAD" else method)
    return None if required is None else list(required)


class TenantAutoSchema(AutoSchema):
    """Documents each operation's FR-5 permissions from the view's
    `required_permissions`, so the docs cannot drift from enforcement."""

    def get_operation(self, path, path_regex, path_prefix, method, registry):
        operation = super().get_operation(path, path_regex, path_prefix, method, registry)
        required = required_permissions_for(self.view, self.method)
        if operation is None or not required:
            return operation

        operation["x-required-permissions"] = required
        note = "**Requires permission:** " + ", ".join(f"`{c}`" for c in required)
        description = operation.get("description")
        operation["description"] = f"{description}\n\n{note}" if description else note
        return operation
