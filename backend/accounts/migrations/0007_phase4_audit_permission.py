"""Phase 4 step 1 data: add the audit.view permission and grant it to
existing businesses' Owner roles only (SRS 2.2: the audit log is Owner-only).

Literal codenames, like 0004–0006, so later catalog edits don't change this
migration. Historical models skip TenantModel.save(), so business_id is set
explicitly.
"""

from django.db import migrations

NEW = {
    "audit.view": "View the audit log of sensitive actions.",
}
DEFAULTS = {
    "Owner": list(NEW),
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
        ("accounts", "0006_phase3_purchases_expenses_permissions"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
