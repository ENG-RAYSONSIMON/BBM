"""The daily cleanup job and the scheduler heartbeat."""

import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import PasswordResetToken
from catalog.tests.helpers import make_owner
from core.tenancy import tenant_context
from notifications.models import Notification


class CleanupTests(TestCase):
    def setUp(self):
        self.user_a, self.business_a = make_owner("a@example.com", "Shop A")
        self.user_b, self.business_b = make_owner("b@example.com", "Shop B")

    def token(self, n, expires_in=timedelta(minutes=30), **fields):
        return PasswordResetToken.objects.create(
            user=self.user_a, token_hash=str(n) * 64, expires_at=timezone.now() + expires_in, **fields
        )

    def notification(self, business, key, resolved_days_ago=None):
        resolved_at = None if resolved_days_ago is None else timezone.now() - timedelta(days=resolved_days_ago)
        with tenant_context(business):
            return Notification.objects.create(kind="LOW_STOCK", dedupe_key=key, resolved_at=resolved_at)

    def test_deletes_only_what_is_no_longer_needed(self):
        live = self.token(1)
        self.token(2, used_at=timezone.now())
        self.token(3, expires_in=timedelta(seconds=-1))
        # In both businesses: old resolved notifications go; open and recent ones stay.
        keep = []
        for business in (self.business_a, self.business_b):
            self.notification(business, "old", resolved_days_ago=91)
            keep.append(self.notification(business, "recent", resolved_days_ago=10).pk)
            keep.append(self.notification(business, "open").pk)

        out = StringIO()
        call_command("cleanup", stdout=out)

        self.assertEqual(list(PasswordResetToken.objects.values_list("pk", flat=True)), [live.pk])
        self.assertCountEqual(Notification.all_objects.values_list("pk", flat=True), keep)
        self.assertIn("Cleanup: 2 reset tokens, 2 old notifications deleted.", out.getvalue())

    @override_settings(NOTIFICATION_RETENTION_DAYS=5)
    def test_retention_comes_from_settings(self):
        self.notification(self.business_a, "recent", resolved_days_ago=10)
        call_command("cleanup", stdout=StringIO())
        self.assertFalse(Notification.all_objects.exists())

    def test_clean_runs_touch_the_heartbeat(self):
        with tempfile.TemporaryDirectory() as folder:
            heartbeat = Path(folder) / "heartbeat"
            with override_settings(SCHEDULER_HEARTBEAT_FILE=str(heartbeat)):
                call_command("cleanup", stdout=StringIO())
                self.assertTrue(heartbeat.exists())
                heartbeat.unlink()
                call_command("generate_notifications", stdout=StringIO())
                self.assertTrue(heartbeat.exists())

    def test_a_failed_run_leaves_the_heartbeat_alone(self):
        # The healthcheck relies on this: only clean runs count as alive.
        with tempfile.TemporaryDirectory() as folder:
            heartbeat = Path(folder) / "heartbeat"
            with override_settings(SCHEDULER_HEARTBEAT_FILE=str(heartbeat)):
                with mock.patch.object(Notification.objects, "filter", side_effect=RuntimeError("broken")):
                    with self.assertRaises(CommandError):
                        call_command("cleanup", stdout=StringIO(), stderr=StringIO())
                self.assertFalse(heartbeat.exists())
