"""Phase 3 step 2 data: add the purchases and expenses permissions and grant
them to existing businesses' system roles (Owner: all; Admin: all but
expenses.delete).

Literal codenames, like 0004/0005, so later catalog edits don't change this
migration. Historical models skip TenantModel.save(), so business_id is set
explicitly.
"""

from django.db import migrations

NEW = {
    "purchases.view": "View purchases from suppliers.",
    "purchases.manage": "Create, edit, receive and cancel purchases.",
    "expenses.view": "View expenses, expense categories and expense totals.",
    "expenses.manage": "Record and edit expenses and their receipts, and manage expense categories.",
    "expenses.delete": "Delete expenses and expense categories.",
}
DEFAULTS = {
    "Owner": list(NEW),
    "Admin": ["purchases.view", "purchases.manage", "expenses.view", "expenses.manage"],
}


def seed(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    RolePermission = apps.get_model("accounts", "RolePermission")

    perms = {}
    for codename, description in NEW.items():
        perms[codename], _ = Permission.objects.get_or_create(
            codename=codename, defaults={"description": description}
        )

    for role_name, codenames in DEFAULTS.items():
        for role in Role.objects.filter(name=role_name, is_system=True):
            for codename in codenames:
                RolePermission.objects.get_or_create(
                    business_id=role.business_id, role=role, permission=perms[codename]
                )


def unseed(apps, schema_editor):
    # Historical models don't fire the Owner-grant pre_delete guard.
    Permission = apps.get_model("accounts", "Permission")
    RolePermission = apps.get_model("accounts", "RolePermission")
    RolePermission.objects.filter(permission__codename__in=NEW).delete()
    Permission.objects.filter(codename__in=NEW).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_phase3_sales_permissions"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
