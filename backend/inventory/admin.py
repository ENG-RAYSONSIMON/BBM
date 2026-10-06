from django.contrib import admin

from core.admin import TenantModelAdmin

from .models import StockMovement


@admin.register(StockMovement)
class StockMovementAdmin(TenantModelAdmin):
    """Read-only: the ledger is append-only (FR-7)."""

    list_display = ("created_at", "movement_type", "quantity", "product", "batch", "business")
    list_filter = ("business", "movement_type")
    list_select_related = ("product", "batch", "business")
    search_fields = ("product__name", "batch__batch_number", "reason")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
