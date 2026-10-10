"""Phase 3 data: add the sales permissions and grant them to existing
businesses' system roles (Owner: all; Admin: view and create, not void).

Literal codenames, like 0004, so later catalog edits don't change this
migration. Historical models skip TenantModel.save(), so business_id is set
explicitly.
"""

from django.db import migrations

SALES = {
    "sales.view": "View sales, payments, customers and sales totals.",
    "sales.create": "Record sales and customer payments, and manage customers.",
    "sales.void": "Void a sale, returning its stock and refunding its payments.",
}
DEFAULTS = {
    "Owner": list(SALES),
    "Admin": ["sales.view", "sales.create"],
}


def seed(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    RolePermission = apps.get_model("accounts", "RolePermission")

    perms = {}
    for codename, description in SALES.items():
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
    RolePermission.objects.filter(permission__codename__in=SALES).delete()
    Permission.objects.filter(codename__in=SALES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_phase2_permissions"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
