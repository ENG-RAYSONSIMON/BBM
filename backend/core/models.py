import uuid

from django.db import models

from .managers import TenantManager
from .tenancy import TenantContextMissing, TenantMismatch, get_current_business_id


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantModel(UUIDModel, TimeStampedModel):
    """Base for every tenant-owned table (FR-3).

    - `objects` only sees rows of the active business and raises
      TenantContextMissing when no business is active.
    - `all_objects` is unscoped: trusted system code only (auth, admin, jobs).
    - `business` is not client-editable; save() fills it from the active
      business and refuses to write into a different one.
    - bulk_create() bypasses save(), so set `business` explicitly there.
    """

    business = models.ForeignKey(
        "accounts.Business",
        on_delete=models.PROTECT,
        editable=False,
        related_name="%(app_label)s_%(class)s_set",
    )

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
        indexes = [models.Index(fields=["business", "id"], name="%(class)s_biz_id_idx")]

    def assign_business(self):
        current = get_current_business_id()
        if self.business_id is None:
            if current is None:
                raise TenantContextMissing(
                    f"Cannot save {type(self).__name__} without an active business."
                )
            self.business_id = current
        elif current is not None and str(self.business_id) != str(current):
            raise TenantMismatch(
                f"{type(self).__name__} belongs to a different business than the active one."
            )

    def save(self, *args, **kwargs):
        self.assign_business()
        super().save(*args, **kwargs)
