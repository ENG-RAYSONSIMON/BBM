"""Staff roles: add the finance, all-sales, payments and staff permissions,
grant them to existing Owner and Admin roles, and create the Seller and
Cashier system roles in every business.

payments.create splits credit repayments out of sales.create; Owner and Admin
get it here, so nothing changes for them. Literal codenames, like 0004–0008.
Historical models skip TenantModel.save(), so business_id is set explicitly.
"""

from django.db import migrations

NEW = {
    "sales.view_all": "View everyone's sales and the sales totals.",
    "payments.create": "Record customer payments towards credit sales.",
    "finance.view": "View buying costs and profit.",
    "staff.manage": "Add staff, change their roles, turn them off and reset their passwords.",
}
GRANTS = {
    "Owner": list(NEW),
    "Admin": list(NEW),
}
SELLER = ["catalog.view", "inventory.view", "sales.view", "sales.create"]
NEW_ROLES = {
    "Seller": SELLER,
    "Cashier": SELLER + ["sales.view_all", "payments.create"],
}


def seed(apps, schema_editor):
    Business = apps.get_model("accounts", "Business")
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    RolePermission = apps.get_model("accounts", "RolePermission")

    for codename, description in NEW.items():
        Permission.objects.get_or_create(codename=codename, defaults={"description": description})
    wanted = set(NEW).union(*NEW_ROLES.values())
    perms = {p.codename: p for p in Permission.objects.filter(codename__in=wanted)}

    for role_name, codenames in GRANTS.items():
        for role in Role.objects.filter(name=role_name, is_system=True):
            for codename in codenames:
                RolePermission.objects.get_or_create(
                    business_id=role.business_id, role=role, permission=perms[codename]
                )

    for business in Business.objects.all():
        for role_name, codenames in NEW_ROLES.items():
            # A business that already made its own role with this name keeps it.
            if Role.objects.filter(business_id=business.pk, name=role_name).exists():
                continue
            role = Role.objects.create(business_id=business.pk, name=role_name, is_system=True)
            for codename in codenames:
                RolePermission.objects.create(
                    business_id=business.pk, role=role, permission=perms[codename]
                )


def unseed(apps, schema_editor):
    # Historical models don't fire the system-role and Owner-grant guards.
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    RolePermission = apps.get_model("accounts", "RolePermission")
    Role.objects.filter(name__in=NEW_ROLES, is_system=True, assignments__isnull=True).delete()
    RolePermission.objects.filter(permission__codename__in=NEW).delete()
    Permission.objects.filter(codename__in=NEW).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_phase4_reports_permissions"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
