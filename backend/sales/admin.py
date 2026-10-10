from django.contrib import admin

from core.admin import TenantModelAdmin

from .models import Customer, Payment, Sale, SaleItem


class ReadOnlyAdmin(TenantModelAdmin):
    """Sales and payments are written only by sales.services (FR-11)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    can_delete = False
    fields = ("product", "quantity", "unit_price", "discount", "line_total", "unit_cost", "line_cost")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        # Admin runs without an active business; the scoped manager would refuse.
        return self.model.all_objects.all()


@admin.register(Sale)
class SaleAdmin(ReadOnlyAdmin):
    list_display = ("number", "created_at", "status", "total", "cost_total", "customer", "business")
    list_filter = ("business", "status")
    list_select_related = ("customer", "business")
    search_fields = ("customer__name", "customer__phone", "note")
    inlines = (SaleItemInline,)


@admin.register(Payment)
class PaymentAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "kind", "method", "amount", "sale", "business")
    list_filter = ("business", "kind", "method")
    list_select_related = ("sale", "business")


@admin.register(Customer)
class CustomerAdmin(ReadOnlyAdmin):
    list_display = ("name", "phone", "business")
    list_filter = ("business",)
    search_fields = ("name", "phone")
