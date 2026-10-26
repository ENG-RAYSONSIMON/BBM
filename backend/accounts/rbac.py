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
CATALOG_VIEW = "catalog.view"
CATALOG_MANAGE = "catalog.manage"
CATALOG_DELETE = "catalog.delete"
INVENTORY_VIEW = "inventory.view"
INVENTORY_ADJUST = "inventory.adjust"
SALES_VIEW = "sales.view"
SALES_CREATE = "sales.create"
SALES_VOID = "sales.void"
PURCHASES_VIEW = "purchases.view"
PURCHASES_MANAGE = "purchases.manage"
EXPENSES_VIEW = "expenses.view"
EXPENSES_MANAGE = "expenses.manage"
EXPENSES_DELETE = "expenses.delete"
AUDIT_VIEW = "audit.view"
REPORTS_VIEW = "reports.view"
REPORTS_EXPORT = "reports.export"

PERMISSIONS = {
    SETTINGS_VIEW: "View business settings.",
    SETTINGS_MANAGE: "Change business settings.",
    CATALOG_VIEW: "View products, categories, brands and suppliers.",
    CATALOG_MANAGE: "Create, edit and archive products, categories, brands and suppliers.",
    CATALOG_DELETE: "Delete products, categories, brands and suppliers.",
    INVENTORY_VIEW: "View stock levels, batches, movements and alerts.",
    INVENTORY_ADJUST: "Record stock adjustments and manage batches.",
    SALES_VIEW: "View sales, payments, customers and sales totals.",
    SALES_CREATE: "Record sales and customer payments, and manage customers.",
    SALES_VOID: "Void a sale, returning its stock and refunding its payments.",
    PURCHASES_VIEW: "View purchases from suppliers.",
    PURCHASES_MANAGE: "Create, edit, receive and cancel purchases.",
    EXPENSES_VIEW: "View expenses, expense categories and expense totals.",
    EXPENSES_MANAGE: "Record and edit expenses and their receipts, and manage expense categories.",
    EXPENSES_DELETE: "Delete expenses and expense categories.",
    AUDIT_VIEW: "View the audit log of sensitive actions.",
    REPORTS_VIEW: "View sales, profit, expense, stock-valuation and expiry reports.",
    REPORTS_EXPORT: "Download reports as CSV.",
}

DEFAULT_ROLE_PERMISSIONS = {
    Role.OWNER: frozenset(PERMISSIONS),
    # SRS 2.2: Admin runs day-to-day operations but cannot delete or read
    # the audit log.
    Role.ADMIN: frozenset(
        {
            SETTINGS_VIEW,
            CATALOG_VIEW,
            CATALOG_MANAGE,
            INVENTORY_VIEW,
            INVENTORY_ADJUST,
            SALES_VIEW,
            SALES_CREATE,
            PURCHASES_VIEW,
            PURCHASES_MANAGE,
            EXPENSES_VIEW,
            EXPENSES_MANAGE,
            REPORTS_VIEW,
            REPORTS_EXPORT,
        }
    ),
}
