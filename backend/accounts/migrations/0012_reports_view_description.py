from django.db import migrations

OLD = "View sales, profit, expense, stock-valuation and expiry reports."
NEW = "View reports: sales; expenses also need expenses.view; profit needs finance.view and expenses.view; stock-valuation and expiry need finance.view."


def set_description(description):
    def run(apps, schema_editor):
        Permission = apps.get_model("accounts", "Permission")
        Permission.objects.filter(codename="reports.view").update(description=description)

    return run


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_cashier_runs_the_shop"),
    ]

    operations = [
        migrations.RunPython(set_description(NEW), set_description(OLD)),
    ]
