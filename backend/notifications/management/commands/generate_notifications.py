from django.core.management.base import BaseCommand, CommandError

from accounts.models import Business
from core.tenancy import tenant_context
from notifications.services import sync_stock_notifications


class Command(BaseCommand):
    help = (
        "Open low-stock and expiry notifications for every active business, and "
        "resolve those whose condition has ended. Safe to run repeatedly (cron)."
    )

    def handle(self, *args, **options):
        opened = resolved = updated = 0
        failed = []
        # System job: it walks every business, activating each one in turn.
        for business in Business.objects.filter(is_active=True).order_by("created_at"):
            try:
                with tenant_context(business):
                    result = sync_stock_notifications()
            except Exception as exc:  # one broken business mustn't stop the rest
                failed.append(business.pk)
                self.stderr.write(f"{business.pk}: {exc!r}")
                continue
            opened += result["opened"]
            resolved += result["resolved"]
            updated += result["updated"]
        self.stdout.write(f"Notifications: {opened} opened, {resolved} resolved, {updated} updated.")
        if failed:
            raise CommandError(f"Failed for {len(failed)} business(es).")
