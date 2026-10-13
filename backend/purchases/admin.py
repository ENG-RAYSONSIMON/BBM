from django.contrib import admin

from core.admin import TenantModelAdmin

from .models import Purchase, PurchaseItem


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0
    can_delete = False
    fields = ("product", "quantity", "unit_cost", "line_total", "batch_number", "expiry_date", "batch")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        # Admin runs without an active business; the scoped manager would refuse.
        return self.model.all_objects.all()


@admin.register(Purchase)
class PurchaseAdmin(TenantModelAdmin):
    """Read-only: purchases are written by purchases.services (FR-14)."""

    list_display = ("purchase_number", "status", "supplier", "purchase_date", "total", "business")
    list_filter = ("business", "status")
    list_select_related = ("supplier", "business")
    search_fields = ("reference", "supplier__name", "note")
    inlines = (PurchaseItemInline,)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
