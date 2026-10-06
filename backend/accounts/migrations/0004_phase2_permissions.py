"""Phase 2 data: add the catalog and inventory permissions and grant them to
existing businesses' system roles (Owner: all; Admin: all but delete).

Literal codenames, like 0003, so later catalog edits don't change this
migration. Historical models skip TenantModel.save(), so business_id is set
explicitly.
"""

from django.db import migrations

CATALOG = {
    "catalog.view": "View products, categories, brands and suppliers.",
    "catalog.manage": "Create, edit and archive products, categories, brands and suppliers.",
    "catalog.delete": "Delete products, categories, brands and suppliers.",
    "inventory.view": "View stock levels, batches, movements and alerts.",
    "inventory.adjust": "Record stock adjustments and manage batches.",
}
DEFAULTS = {
    "Owner": list(CATALOG),
    "Admin": ["catalog.view", "catalog.manage", "inventory.view", "inventory.adjust"],
}


def seed(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    RolePermission = apps.get_model("accounts", "RolePermission")

    perms = {}
    for codename, description in CATALOG.items():
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
    RolePermission.objects.filter(permission__codename__in=CATALOG).delete()
    Permission.objects.filter(codename__in=CATALOG).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_seed_permissions"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
