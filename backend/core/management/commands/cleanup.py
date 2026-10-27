from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from accounts.models import Business, PasswordResetToken
from core.heartbeat import beat
from core.tenancy import tenant_context
from notifications.models import Notification


class Command(BaseCommand):
    help = (
        "Delete rows that are no longer needed: expired login tokens, used or "
        "expired password-reset tokens, and resolved notifications older than "
        "NOTIFICATION_RETENTION_DAYS. Safe to run repeatedly (daily cron)."
    )

    def handle(self, *args, **options):
        now = timezone.now()
        # SimpleJWT's own command: outstanding and blacklisted tokens past expiry.
        call_command("flushexpiredtokens", stdout=self.stdout)

        # Not tenant-owned: reset tokens belong to a user, not a business.
        tokens, _ = PasswordResetToken.objects.filter(Q(used_at__isnull=False) | Q(expires_at__lt=now)).delete()

        cutoff = now - timedelta(days=settings.NOTIFICATION_RETENTION_DAYS)
        notifications = 0
        failed = []
        # System job: it walks every business, activating each one in turn.
        for business in Business.objects.order_by("created_at"):
            try:
                with tenant_context(business):
                    _, deleted = Notification.objects.filter(resolved_at__lt=cutoff).delete()
            except Exception as exc:  # one broken business mustn't stop the rest
                failed.append(business.pk)
                self.stderr.write(f"{business.pk}: {exc!r}")
                continue
            notifications += deleted.get("notifications.Notification", 0)

        self.stdout.write(f"Cleanup: {tokens} reset tokens, {notifications} old notifications deleted.")
        if failed:
            raise CommandError(f"Failed for {len(failed)} business(es).")
        beat()
