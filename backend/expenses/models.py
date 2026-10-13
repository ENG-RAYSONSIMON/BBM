from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from core.models import TenantModel

# Seeded for every business (expenses.services.seed_default_categories).
DEFAULT_CATEGORIES = (
    "Rent",
    "Salaries & wages",
    "Utilities",
    "Transport",
    "Marketing",
    "Supplies",
    "Other",
)


class ExpenseCategory(TenantModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta(TenantModel.Meta):
        verbose_name_plural = "expense categories"
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                "business", Lower("name"), name="expenses_category_unique_name_per_business"
            ),
        ]

    def __str__(self):
        return self.name


class PrivateStorage(FileSystemStorage):
    """Files outside MEDIA_ROOT, so they are never served at /media/. Read
    through the API only. The location is read on use, so tests can
    override PRIVATE_MEDIA_ROOT."""

    def __init__(self):
        super().__init__(base_url=None)

    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return str(settings.PRIVATE_MEDIA_ROOT)

    def url(self, name):
        raise ValueError("Private files have no public URL.")

    def deconstruct(self):
        return ("expenses.models.PrivateStorage", (), {})


private_storage = PrivateStorage()


def receipt_path(instance, filename):
    # The view names the file <uuid>.<ext> after validating it; keep tenants
    # in separate folders. Receipts are only served through the API.
    return f"receipts/{instance.business_id}/{filename}"


class Expense(TenantModel):
    """FR-15 operating cost. Net profit for a period is gross profit minus
    the expenses whose expense_date falls in it (FR-16)."""

    class Method(models.TextChoices):
        CASH = "CASH", "Cash"

    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="expenses")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    expense_date = models.DateField(default=timezone.localdate, help_text="When the money was spent.")
    description = models.CharField(max_length=255)
    paid_to = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    receipt = models.FileField(upload_to=receipt_path, storage=private_storage, null=True, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="expenses"
    )

    class Meta(TenantModel.Meta):
        ordering = ("-expense_date", "-created_at")
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="expenses_expense_amount_positive"),
        ]
        indexes = [
            *TenantModel.Meta.indexes,
            models.Index(fields=["business", "expense_date"], name="expense_biz_date_idx"),
            models.Index(fields=["business", "created_at"], name="expense_biz_created_idx"),
        ]

    def __str__(self):
        return f"{self.expense_date} {self.description} {self.amount}"

    def save(self, *args, **kwargs):
        self.assign_business()
        self.check_same_business("category")
        super().save(*args, **kwargs)
