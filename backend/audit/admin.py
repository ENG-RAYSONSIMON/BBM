from django.contrib import admin

from core.admin import TenantModelAdmin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(TenantModelAdmin):
    """Read-only: entries are append-only."""

    list_display = ("created_at", "action", "target_type", "target_label", "actor", "business")
    list_filter = ("business", "action")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
