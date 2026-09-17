"""FR-5 permission catalog and the default grants for seeded roles.

Role names appear here only to seed new businesses. Access decisions read
RolePermission rows (core.permissions.HasTenantPermission), so a role's
powers can change, or a new role be added, without touching code.

Adding a permission: add it to PERMISSIONS, add it to the defaults, and write
a data migration that inserts the catalog row and grants it to existing
businesses' roles.
"""

from .models import Role

SETTINGS_VIEW = "settings.view"
SETTINGS_MANAGE = "settings.manage"

PERMISSIONS = {
    SETTINGS_VIEW: "View business settings.",
    SETTINGS_MANAGE: "Change business settings.",
}

DEFAULT_ROLE_PERMISSIONS = {
    Role.OWNER: frozenset(PERMISSIONS),
    Role.ADMIN: frozenset({SETTINGS_VIEW}),
}
