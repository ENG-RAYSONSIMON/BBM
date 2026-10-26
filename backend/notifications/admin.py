from django.contrib import admin

from core.admin import TenantModelAdmin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(TenantModelAdmin):
    list_display = ("created_at", "kind", "dedupe_key", "resolved_at", "business")
    list_filter = ("business", "kind")
    readonly_fields = ("business", "params")
