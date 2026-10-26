from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from core.managers import TenantManager, TenantQuerySet
from core.models import TenantModel


class AuditLogImmutable(RuntimeError):
    """Audit entries are append-only: never updated or deleted."""


class AuditLogQuerySet(TenantQuerySet):
    """update() and bulk_update() write SQL directly, skipping save(), so
    they are refused here."""

    def update(self, **kwargs):
        raise AuditLogImmutable("Audit entries cannot be changed.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise AuditLogImmutable("Audit entries cannot be changed.")


class AuditLog(TenantModel):
    """FR-20: one row per sensitive action. Written by audit.services.record()
    in the same transaction as the action, so a rolled-back action leaves no
    entry. Readable only with `audit.view` (Owner)."""

    class Action(models.TextChoices):
        DELETE = "DELETE", "Delete"
        SETTINGS_CHANGE = "SETTINGS_CHANGE", "Settings change"
        ROLE_CHANGE = "ROLE_CHANGE", "Role change"
        SALE_VOID = "SALE_VOID", "Sale void"
        PURCHASE_CANCEL = "PURCHASE_CANCEL", "Purchase cancel"
        EXPENSE_CHANGE = "EXPENSE_CHANGE", "Expense change"
        EXPORT = "EXPORT", "Export"
        STAFF_ADD = "STAFF_ADD", "Staff added"
        STAFF_CHANGE = "STAFF_CHANGE", "Staff changed"
        STAFF_PASSWORD_RESET = "STAFF_PASSWORD_RESET", "Staff password reset"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="audit_logs",
        help_text="Empty for system actions.",
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    target_type = models.CharField(max_length=50, blank=True, help_text="Model name, e.g. product.")
    target_id = models.UUIDField(null=True, blank=True)
    target_label = models.CharField(
        max_length=255, blank=True, help_text="The target's name when the action happened."
    )
    changes = models.JSONField(
        default=dict, blank=True, encoder=DjangoJSONEncoder, help_text="{field: [old, new]} or details."
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    objects = TenantManager.from_queryset(AuditLogQuerySet)()
    all_objects = models.Manager.from_queryset(AuditLogQuerySet)()

    class Meta(TenantModel.Meta):
        ordering = ("-created_at",)
        indexes = [
            *TenantModel.Meta.indexes,
            models.Index(fields=["business", "created_at"], name="audit_biz_created_idx"),
            models.Index(fields=["business", "action"], name="audit_biz_action_idx"),
        ]

    def __str__(self):
        return f"{self.action} {self.target_type} {self.target_label}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditLogImmutable("Audit entries cannot be changed.")
        super().save(*args, **kwargs)


# pre_delete also covers QuerySet deletes (Django sends it per object).
@receiver(pre_delete, sender=AuditLog)
def protect_audit_log(sender, instance, **kwargs):
    raise AuditLogImmutable("Audit entries cannot be deleted.")
