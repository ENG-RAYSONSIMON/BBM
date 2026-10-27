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
SALES_VIEW_ALL = "sales.view_all"
PAYMENTS_CREATE = "payments.create"
FINANCE_VIEW = "finance.view"
STAFF_MANAGE = "staff.manage"

PERMISSIONS = {
    SETTINGS_VIEW: "View business settings.",
    SETTINGS_MANAGE: "Change business settings.",
    CATALOG_VIEW: "View products, categories, brands and suppliers.",
    CATALOG_MANAGE: "Create, edit and archive products, categories, brands and suppliers.",
    CATALOG_DELETE: "Delete products, categories, brands and suppliers.",
    INVENTORY_VIEW: "View stock levels, batches, movements and alerts.",
    INVENTORY_ADJUST: "Record stock adjustments and manage batches.",
    SALES_VIEW: "View sales, payments and customers (only your own sales without sales.view_all).",
    SALES_CREATE: "Record sales and manage customers.",
    SALES_VOID: "Void a sale, returning its stock and refunding its payments.",
    PURCHASES_VIEW: "View purchases from suppliers.",
    PURCHASES_MANAGE: "Create, edit, receive and cancel purchases.",
    EXPENSES_VIEW: "View expenses, expense categories and expense totals.",
    EXPENSES_MANAGE: "Record and edit expenses and their receipts, and manage expense categories.",
    EXPENSES_DELETE: "Delete expenses and expense categories.",
    AUDIT_VIEW: "View the audit log of sensitive actions.",
    REPORTS_VIEW: "View reports: sales; expenses also need expenses.view; profit needs finance.view and expenses.view; stock-valuation and expiry need finance.view.",
    REPORTS_EXPORT: "Download reports as CSV.",
    SALES_VIEW_ALL: "View everyone's sales and the sales totals.",
    PAYMENTS_CREATE: "Record customer payments towards credit sales.",
    FINANCE_VIEW: "View buying costs and profit.",
    STAFF_MANAGE: "Add staff, change their roles, turn them off and reset their passwords.",
}

SELLER_PERMISSIONS = frozenset({CATALOG_VIEW, INVENTORY_VIEW, SALES_VIEW, SALES_CREATE})

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
            SALES_VIEW_ALL,
            PAYMENTS_CREATE,
            FINANCE_VIEW,
            STAFF_MANAGE,
        }
    ),
    # Sellers sell and see stock; they see only their own sales and never
    # buying costs or profit.
    Role.SELLER: SELLER_PERMISSIONS,
    # The cashier runs the shop's money path for an owner who may be far
    # away: sales and repayments, products and stock, purchases and expenses,
    # with buying costs and profit. Never deletes or voids, and has no
    # reports, settings or staff (so it stays below Admin).
    Role.CASHIER: SELLER_PERMISSIONS
    | {
        SALES_VIEW_ALL,
        PAYMENTS_CREATE,
        FINANCE_VIEW,
        CATALOG_MANAGE,
        INVENTORY_ADJUST,
        PURCHASES_VIEW,
        PURCHASES_MANAGE,
        EXPENSES_VIEW,
        EXPENSES_MANAGE,
    },
}
