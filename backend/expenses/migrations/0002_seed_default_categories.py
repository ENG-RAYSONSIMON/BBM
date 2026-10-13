"""Give businesses that existed before expenses the default categories.
New businesses get them at registration (accounts.services.register_owner).

Literal names, so later edits to DEFAULT_CATEGORIES don't change this
migration. Historical models skip TenantModel.save(), so business_id is set
explicitly.
"""

from django.db import migrations
from django.db.models.functions import Lower

DEFAULTS = ("Rent", "Salaries & wages", "Utilities", "Transport", "Marketing", "Supplies", "Other")


def seed(apps, schema_editor):
    Business = apps.get_model("accounts", "Business")
    ExpenseCategory = apps.get_model("expenses", "ExpenseCategory")
    for business in Business.objects.all():
        existing = set(
            ExpenseCategory.objects.filter(business_id=business.pk)
            .annotate(lower=Lower("name"))
            .values_list("lower", flat=True)
        )
        for name in DEFAULTS:
            if name.lower() not in existing:
                ExpenseCategory.objects.create(business_id=business.pk, name=name)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_phase3_purchases_expenses_permissions"),
        ("expenses", "0001_initial"),
    ]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
