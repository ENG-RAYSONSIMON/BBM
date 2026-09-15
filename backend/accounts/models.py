from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower

from core.models import TenantModel, TimeStampedModel, UUIDModel
from core.tenancy import TenantMismatch

from .managers import UserManager


class User(UUIDModel, TimeStampedModel, AbstractUser):
    """Login identity. Not tenant-scoped: businesses are reached via UserRole."""

    username = None
    email = models.EmailField("email address", unique=True)
    phone = models.CharField(max_length=20, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
        ]

    def __str__(self):
        return self.email


class Business(UUIDModel, TimeStampedModel):
    """A tenant. Tenant-owned tables point here via TenantModel.business."""

    name = models.CharField(max_length=255)
    tin = models.CharField("TIN", max_length=50, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    currency = models.CharField(max_length=3, default="TZS")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "businesses"

    def __str__(self):
        return self.name


class Role(TenantModel):
    OWNER = "Owner"

    name = models.CharField(max_length=50)
    is_system = models.BooleanField(
        default=False, help_text="System roles (e.g. Owner) cannot be renamed or removed."
    )

    class Meta(TenantModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["business", "name"], name="accounts_role_unique_name_per_business"
            ),
        ]

    def __str__(self):
        return self.name


class UserRole(TenantModel):
    """A user's membership of a business, with one role per business."""

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="assignments")
    is_active = models.BooleanField(default=True)

    class Meta(TenantModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["business", "user"], name="accounts_userrole_unique_user_per_business"
            ),
        ]

    def __str__(self):
        return f"{self.user} — {self.role}"

    def save(self, *args, **kwargs):
        self.assign_business()
        if str(self.role.business_id) != str(self.business_id):
            raise TenantMismatch("UserRole.role belongs to a different business.")
        super().save(*args, **kwargs)


class BusinessSettings(TenantModel):
    """Per-business configuration; exactly one row per business."""

    low_stock_threshold = models.PositiveIntegerField(default=5)
    expiry_warning_days = models.PositiveIntegerField(default=30)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    loyalty_enabled = models.BooleanField(default=False)

    class Meta(TenantModel.Meta):
        verbose_name = "business settings"
        verbose_name_plural = "business settings"
        constraints = [
            models.UniqueConstraint(
                fields=["business"], name="accounts_businesssettings_one_per_business"
            ),
        ]

    def __str__(self):
        return f"Settings for {self.business_id}"
