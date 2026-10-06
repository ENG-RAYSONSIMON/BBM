from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from core.models import TenantModel


def _unique_name(model_name):
    """Case-insensitive name uniqueness within one business."""
    return models.UniqueConstraint(
        "business", Lower("name"), name=f"catalog_{model_name}_unique_name_per_business"
    )


class Category(TenantModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta(TenantModel.Meta):
        verbose_name_plural = "categories"
        ordering = ("name",)
        constraints = [_unique_name("category")]

    def __str__(self):
        return self.name


class Brand(TenantModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta(TenantModel.Meta):
        ordering = ("name",)
        constraints = [_unique_name("brand")]

    def __str__(self):
        return self.name


class Supplier(TenantModel):
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta(TenantModel.Meta):
        ordering = ("name",)
        constraints = [_unique_name("supplier")]

    def __str__(self):
        return self.name


def product_image_path(instance, filename):
    # The view names the file <uuid>.<ext> after validating it; keep tenants
    # in separate folders.
    return f"products/{instance.business_id}/{filename}"


class Product(TenantModel):
    """A catalog item. Stock is never stored here: it is the sum of the
    product's stock movements (inventory.StockMovement, FR-8)."""

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    sku = models.CharField("SKU", max_length=64, blank=True)
    barcode = models.CharField(max_length=64, blank=True)
    unit = models.CharField(max_length=20, default="pcs")
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, null=True, blank=True, related_name="products"
    )
    brand = models.ForeignKey(
        Brand, on_delete=models.PROTECT, null=True, blank=True, related_name="products"
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, null=True, blank=True, related_name="products"
    )
    # Current prices. Phase 3 sale/purchase items snapshot them, so changing
    # these never rewrites past profit.
    selling_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    cost_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    reorder_level = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Low-stock threshold for this product. Empty uses the business setting.",
    )
    tracks_expiry = models.BooleanField(
        default=True, help_text="Batches of this product need an expiry date."
    )
    image = models.ImageField(upload_to=product_image_path, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(TenantModel.Meta):
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["business", "sku"],
                condition=~Q(sku=""),
                name="catalog_product_unique_sku_per_business",
            ),
            models.UniqueConstraint(
                fields=["business", "barcode"],
                condition=~Q(barcode=""),
                name="catalog_product_unique_barcode_per_business",
            ),
            models.CheckConstraint(
                condition=Q(selling_price__gte=0) & Q(cost_price__gte=0),
                name="catalog_product_prices_not_negative",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.assign_business()
        self.check_same_business("category", "brand", "supplier")
        super().save(*args, **kwargs)


class ProductBatch(TenantModel):
    """A lot of one product. Stock is held per batch (sum of its movements),
    so expiry views know how many expiring units are actually left."""

    DEFAULT_NUMBER = "DEFAULT"

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="batches")
    batch_number = models.CharField(max_length=64)
    expiry_date = models.DateField(null=True, blank=True)
    received_on = models.DateField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        verbose_name_plural = "product batches"
        ordering = ("expiry_date", "batch_number")
        constraints = [
            models.UniqueConstraint(
                fields=["product", "batch_number"], name="catalog_batch_unique_number_per_product"
            ),
        ]
        indexes = [
            *TenantModel.Meta.indexes,
            models.Index(fields=["business", "expiry_date"], name="batch_biz_expiry_idx"),
        ]

    def __str__(self):
        return f"{self.product} — {self.batch_number}"

    def save(self, *args, **kwargs):
        self.assign_business()
        self.check_same_business("product")
        super().save(*args, **kwargs)
