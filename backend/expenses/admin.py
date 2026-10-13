from django.contrib import admin

from core.admin import TenantModelAdmin

from .models import Expense, ExpenseCategory


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(TenantModelAdmin):
    list_display = ("name", "business")
    search_fields = ("name",)


@admin.register(Expense)
class ExpenseAdmin(TenantModelAdmin):
    list_display = ("expense_date", "description", "category", "amount", "business")
    list_filter = ("business", "category")
    list_select_related = ("category", "business")
    search_fields = ("description", "paid_to")
    # Receipts are uploaded (and validated) only through the API, and have no URL.
    exclude = ("receipt",)
    readonly_fields = ("business", "has_receipt")

    @admin.display(boolean=True)
    def has_receipt(self, obj):
        return bool(obj.receipt)
