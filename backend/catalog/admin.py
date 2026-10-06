from django.contrib import admin

from core.admin import TenantModelAdmin

from .models import Brand, Category, Product, ProductBatch, Supplier


@admin.register(Category)
class CategoryAdmin(TenantModelAdmin):
    list_display = ("name", "business")
    search_fields = ("name",)


@admin.register(Brand)
class BrandAdmin(TenantModelAdmin):
    list_display = ("name", "business")
    search_fields = ("name",)


@admin.register(Supplier)
class SupplierAdmin(TenantModelAdmin):
    list_display = ("name", "contact_person", "phone", "business")
    search_fields = ("name", "contact_person", "phone", "email")


@admin.register(Product)
class ProductAdmin(TenantModelAdmin):
    list_display = ("name", "sku", "selling_price", "is_active", "business")
    list_filter = ("business", "is_active")
    list_select_related = ("business",)
    search_fields = ("name", "sku", "barcode")


@admin.register(ProductBatch)
class ProductBatchAdmin(TenantModelAdmin):
    list_display = ("product", "batch_number", "expiry_date", "business")
    list_select_related = ("product", "business")
    search_fields = ("batch_number", "product__name")
