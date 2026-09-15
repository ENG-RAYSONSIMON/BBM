from django.contrib import admin

from .models import TenantModel


class TenantModelAdmin(admin.ModelAdmin):
    """Admin runs without a tenant, so it reads through the unscoped manager.

    Adding rows is disabled: tenant rows are created by services that activate
    the owning business first.
    """

    readonly_fields = ("business",)
    list_filter = ("business",)

    def get_queryset(self, request):
        queryset = self.model.all_objects.get_queryset()
        ordering = self.get_ordering(request)
        if ordering:
            queryset = queryset.order_by(*ordering)
        return queryset

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if issubclass(db_field.related_model, TenantModel):
            kwargs.setdefault("queryset", db_field.related_model.all_objects.all())
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def has_add_permission(self, request):
        return False
