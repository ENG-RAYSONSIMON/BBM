from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Q

from core.models import TenantModel


class Notification(TenantModel):
    """FR-19: one alert in the in-app notification centre.

    The text isn't stored: `kind` plus `params` (a snapshot such as the
    product name and stock) are rendered by the client in the reader's
    language. A notification is *open* while its condition lasts and is
    resolved when it ends, so a product that stays low gets one alert, not
    one per run (`dedupe_key` is unique among open notifications)."""

    class Kind(models.TextChoices):
        LOW_STOCK = "LOW_STOCK", "Low stock"
        EXPIRING = "EXPIRING", "Expiring soon"
        EXPIRED = "EXPIRED", "Expired"

    class Channel(models.TextChoices):
        IN_APP = "IN_APP", "In app"
        # Reserved: interfaces exist (notifications.channels) but no provider
        # is wired until Phase 5, and using one fails visibly.
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"
        WHATSAPP = "WHATSAPP", "WhatsApp"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.IN_APP)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
        help_text="Empty: everyone in the business who holds `required_permission`.",
    )
    required_permission = models.CharField(
        max_length=100, blank=True, help_text="Codename a reader needs; empty for any member."
    )
    params = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    target_type = models.CharField(max_length=50, blank=True)
    target_id = models.UUIDField(null=True, blank=True)
    dedupe_key = models.CharField(max_length=200)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["business", "dedupe_key"],
                condition=Q(resolved_at__isnull=True),
                name="notification_one_open_per_key",
            ),
        ]
        indexes = [
            *TenantModel.Meta.indexes,
            models.Index(fields=["business", "created_at"], name="notification_biz_created_idx"),
        ]

    def __str__(self):
        return f"{self.kind} {self.dedupe_key}"


class NotificationRead(TenantModel):
    """Who has read which notification: read state is per user, since one
    business-wide notification reaches several people."""

    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name="reads")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")

    class Meta(TenantModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["notification", "user"], name="notification_read_once"),
        ]

    def save(self, *args, **kwargs):
        self.assign_business()
        self.check_same_business("notification")
        super().save(*args, **kwargs)
