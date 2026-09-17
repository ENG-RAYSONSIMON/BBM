"""FR-5 data: insert the initial permission catalog and give every existing
business an Admin role, with default grants for its Owner and Admin roles.

Codenames are literals rather than imports from accounts.rbac, so later
catalog changes cannot alter what this migration does. Historical models skip
TenantModel.save(), so business_id is set explicitly.
"""

from django.db import migrations

CATALOG = {
    "settings.view": "View business settings.",
    "settings.manage": "Change business settings.",
}
DEFAULTS = {
    "Owner": ["settings.view", "settings.manage"],
    "Admin": ["settings.view"],
}


def seed(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Business = apps.get_model("accounts", "Business")
    Role = apps.get_model("accounts", "Role")
    RolePermission = apps.get_model("accounts", "RolePermission")

    perms = {}
    for codename, description in CATALOG.items():
        perms[codename], _ = Permission.objects.get_or_create(
            codename=codename, defaults={"description": description}
        )

    for business in Business.objects.all():
        for role_name, codenames in DEFAULTS.items():
            role, _ = Role.objects.get_or_create(
                business_id=business.pk, name=role_name, defaults={"is_system": True}
            )
            for codename in codenames:
                RolePermission.objects.get_or_create(
                    business_id=business.pk, role=role, permission=perms[codename]
                )


def unseed(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    RolePermission = apps.get_model("accounts", "RolePermission")
    RolePermission.objects.filter(permission__codename__in=CATALOG).delete()
    Permission.objects.filter(codename__in=CATALOG).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_rbac_and_password_reset"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
