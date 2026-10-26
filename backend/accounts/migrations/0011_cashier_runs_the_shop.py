"""The Cashier runs the shop's money path: give existing businesses' system
Cashier roles products, stock, purchases, expenses and buying costs/profit.
Deletes, voids, reports, settings and staff stay with Owner (and Admin).

Literal codenames, like 0004–0009. Historical models skip TenantModel.save(),
so business_id is set explicitly.
"""

from django.db import migrations

NEW = [
    "finance.view",
    "catalog.manage",
    "inventory.adjust",
    "purchases.view",
    "purchases.manage",
    "expenses.view",
    "expenses.manage",
]


def grant(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    RolePermission = apps.get_model("accounts", "RolePermission")

    perms = list(Permission.objects.filter(codename__in=NEW))
    for role in Role.objects.filter(name="Cashier", is_system=True):
        for permission in perms:
            RolePermission.objects.get_or_create(
                business_id=role.business_id, role=role, permission=permission
            )


def revoke(apps, schema_editor):
    RolePermission = apps.get_model("accounts", "RolePermission")
    RolePermission.objects.filter(
        role__name="Cashier", role__is_system=True, permission__codename__in=NEW
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_user_must_change_password"),
    ]

    operations = [migrations.RunPython(grant, revoke)]
