"""FR-19: stock alerts are opened and resolved idempotently, read state is
per user, visibility follows permissions and the business, and outside
channels fail visibly."""

from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.urls import reverse
from django.utils import timezone

from accounts.models import BusinessSettings
from catalog.tests.helpers import TenantAPITestCase, days, make_member, make_product, stock
from core.tenancy import tenant_context
from inventory.models import StockMovement
from notifications.channels import ChannelNotConfigured, deliver
from notifications.models import Notification, NotificationRead
from notifications.services import sync_stock_notifications

LIST_URL = reverse("notifications:notification-list")
COUNT_URL = reverse("notifications:notification-unread-count")
READ_ALL_URL = reverse("notifications:notification-read-all")


def read_url(pk):
    return reverse("notifications:notification-read", args=[pk])


def run():
    out = StringIO()
    call_command("generate_notifications", stdout=out)
    return out.getvalue()


def open_alerts(business):
    return Notification.all_objects.filter(business=business, resolved_at__isnull=True)


class GenerateTests(TenantAPITestCase):
    """Low stock threshold is 5 by default; expiry warning is 30 days."""

    def setUp(self):
        super().setUp()
        self.shea = make_product(self.business_a, "Shea Butter")
        self.batch = stock(self.business_a, self.shea, 3, self.owner_a, expiry_date=days(10))

    def test_opens_low_stock_and_expiring_alerts_once(self):
        self.assertIn("2 opened, 0 resolved", run())
        alerts = {n.kind: n for n in open_alerts(self.business_a)}
        self.assertEqual(set(alerts), {"LOW_STOCK", "EXPIRING"})
        low = alerts["LOW_STOCK"]
        self.assertEqual(low.params["name"], "Shea Butter")
        self.assertEqual(low.params["stock"], 3)
        self.assertEqual((low.target_type, low.target_id), ("product", self.shea.pk))
        self.assertEqual(low.required_permission, "inventory.view")
        self.assertEqual(alerts["EXPIRING"].params["days"], 10)

        self.assertIn("0 opened, 0 resolved", run())  # nothing new
        self.assertEqual(open_alerts(self.business_a).count(), 2)

    def test_resolves_when_the_condition_ends_and_reopens_when_it_returns(self):
        run()
        stock(self.business_a, self.shea, -3, self.owner_a, movement_type=StockMovement.Type.DAMAGE)
        stock(self.business_a, self.shea, 20, self.owner_a, batch_number="B2", expiry_date=days(300))
        # Restocked from a fresh batch, and the expiring batch is empty.
        self.assertIn("0 opened, 2 resolved", run())
        self.assertEqual(open_alerts(self.business_a).count(), 0)

        stock(self.business_a, self.shea, -18, self.owner_a, batch_number="B2", movement_type=StockMovement.Type.DAMAGE)
        self.assertIn("1 opened", run())
        self.assertEqual(Notification.all_objects.filter(business=self.business_a, kind="LOW_STOCK").count(), 2)

    def test_expired_batch_and_archived_products(self):
        stock(self.business_a, self.shea, 10, self.owner_a, batch_number="OLD", expiry_date=days(-2))
        archived = make_product(self.business_a, "Rose Water", is_active=False)
        stock(self.business_a, archived, 1, self.owner_a)
        run()
        kinds = sorted(open_alerts(self.business_a).values_list("kind", flat=True))
        # 13 in stock: not low. Rose Water is archived: no alert.
        self.assertEqual(kinds, ["EXPIRED", "EXPIRING"])
        self.assertEqual(open_alerts(self.business_a).get(kind="EXPIRED").params["batch_number"], "OLD")

    def test_each_business_gets_its_own_alerts(self):
        make_product(self.business_b, "Aloe Gel")  # 0 in stock: low
        run()
        self.assertEqual(open_alerts(self.business_a).count(), 2)
        self.assertEqual(list(open_alerts(self.business_b).values_list("params__name", flat=True)), ["Aloe Gel"])

    def test_open_alerts_keep_their_figures_current(self):
        run()
        stock(self.business_a, self.shea, -1, self.owner_a, movement_type=StockMovement.Type.DAMAGE)
        with tenant_context(self.business_a):
            result = sync_stock_notifications(today=days(3))
        self.assertEqual((result["opened"], result["resolved"], result["updated"]), (0, 0, 2))
        alerts = {n.kind: n for n in open_alerts(self.business_a)}
        self.assertEqual(alerts["LOW_STOCK"].params["stock"], 2)
        self.assertEqual(alerts["EXPIRING"].params["days"], 7)
        self.assertEqual(alerts["EXPIRING"].params["expiry_date"], days(10).isoformat())
        with tenant_context(self.business_a):
            self.assertEqual(sync_stock_notifications(today=days(3))["updated"], 0)

    def test_a_failed_run_changes_nothing(self):
        run()
        stock(self.business_a, self.shea, -3, self.owner_a, movement_type=StockMovement.Type.DAMAGE)
        make_product(self.business_a, "Rose Water")  # would open a new alert
        with mock.patch.object(Notification.objects, "bulk_create", side_effect=RuntimeError("boom")):
            with tenant_context(self.business_a), self.assertRaises(RuntimeError):
                sync_stock_notifications()
        # The expiring alert would have been resolved: the rollback kept it open.
        self.assertEqual(sorted(open_alerts(self.business_a).values_list("kind", flat=True)), ["EXPIRING", "LOW_STOCK"])

    def test_one_broken_business_does_not_stop_the_others(self):
        BusinessSettings.all_objects.filter(business=self.business_b).delete()
        out, err = StringIO(), StringIO()
        with self.assertRaises(CommandError):
            call_command("generate_notifications", stdout=out, stderr=err)
        self.assertEqual(open_alerts(self.business_a).count(), 2)
        self.assertIn(str(self.business_b.pk), err.getvalue())

    def test_service_is_idempotent_within_a_business(self):
        with tenant_context(self.business_a):
            first = sync_stock_notifications()
            second = sync_stock_notifications()
        self.assertEqual((first["opened"], second["opened"]), (2, 0))


class CentreAPITests(TenantAPITestCase):
    def setUp(self):
        super().setUp()
        make_product(self.business_a, "Shea Butter")  # out of stock: low
        make_product(self.business_a, "Rose Water")
        run()
        self.as_user(self.owner_a, self.business_a)

    def test_list_and_unread_count(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["results"][0]["kind"], "LOW_STOCK")
        self.assertFalse(response.data["results"][0]["is_read"])
        self.assertEqual(self.client.get(COUNT_URL).data, {"unread": 2})

    def test_read_state_is_per_user(self):
        first = self.client.get(LIST_URL).data["results"][0]["id"]
        self.assertEqual(self.client.post(read_url(first)).status_code, 204)
        self.assertEqual(self.client.post(read_url(first)).status_code, 204)  # again: no error
        self.assertEqual(self.client.get(COUNT_URL).data, {"unread": 1})
        self.assertEqual(self.client.get(LIST_URL, {"unread": "true"}).data["count"], 1)

        self.as_user(self.admin_a, self.business_a)  # admin holds inventory.view
        self.assertEqual(self.client.get(COUNT_URL).data, {"unread": 2})
        self.assertEqual(self.client.post(READ_ALL_URL).status_code, 204)
        self.assertEqual(self.client.get(COUNT_URL).data, {"unread": 0})

        self.as_user(self.owner_a, self.business_a)
        self.assertEqual(self.client.get(COUNT_URL).data, {"unread": 1})

    def test_read_all_marks_only_what_the_caller_sees(self):
        with tenant_context(self.business_a):
            Notification.objects.create(kind="LOW_STOCK", recipient=self.admin_a, dedupe_key="personal")
        cashier = make_member(self.business_a, "cashier@example.com", "Cashier")
        self.as_user(cashier, self.business_a)  # no inventory.view: sees nothing
        self.assertEqual(self.client.post(READ_ALL_URL).status_code, 204)
        self.assertFalse(NotificationRead.all_objects.filter(user=cashier).exists())

        self.as_user(self.owner_a, self.business_a)
        self.client.post(READ_ALL_URL)
        self.assertEqual(NotificationRead.all_objects.filter(user=self.owner_a).count(), 2)
        self.as_user(self.admin_a, self.business_a)  # admin's own reads untouched, personal one included
        self.assertEqual(self.client.get(COUNT_URL).data, {"unread": 3})

    def test_resolved_alerts_stay_listed_but_not_counted(self):
        open_alerts(self.business_a).update(resolved_at=timezone.now())
        self.assertEqual(self.client.get(COUNT_URL).data, {"unread": 0})
        self.assertEqual(self.client.get(LIST_URL).data["count"], 2)
        self.assertEqual(self.client.get(LIST_URL, {"open": "true"}).data["count"], 0)

    def test_needs_the_alerts_permission(self):
        cashier = make_member(self.business_a, "cashier@example.com", "Cashier")
        self.as_user(cashier, self.business_a)
        self.assertEqual(self.client.get(LIST_URL).data["count"], 0)
        self.assertEqual(self.client.get(COUNT_URL).data, {"unread": 0})
        hidden = Notification.all_objects.filter(business=self.business_a).first()
        self.assertEqual(self.client.get(reverse("notifications:notification-detail", args=[hidden.pk])).status_code, 404)
        self.assertEqual(self.client.post(read_url(hidden.pk)).status_code, 404)

    def test_personal_notifications_reach_only_their_recipient(self):
        with tenant_context(self.business_a):
            Notification.objects.create(kind="LOW_STOCK", recipient=self.admin_a, dedupe_key="personal")
        self.assertEqual(self.client.get(LIST_URL).data["count"], 2)
        self.as_user(self.admin_a, self.business_a)
        self.assertEqual(self.client.get(LIST_URL).data["count"], 3)

    def test_no_writes_besides_read_state(self):
        pk = self.client.get(LIST_URL).data["results"][0]["id"]
        detail = reverse("notifications:notification-detail", args=[pk])
        self.assertEqual(self.client.post(LIST_URL, {"kind": "LOW_STOCK"}, format="json").status_code, 405)
        self.assertEqual(self.client.patch(detail, {"kind": "EXPIRED"}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(detail).status_code, 405)

    def test_another_business_sees_nothing(self):
        pk = self.client.get(LIST_URL).data["results"][0]["id"]
        self.as_user(self.owner_b, self.business_b)
        self.assertEqual(self.client.get(LIST_URL).data["count"], 0)
        self.assertEqual(self.client.get(reverse("notifications:notification-detail", args=[pk])).status_code, 404)
        self.assertEqual(self.client.post(read_url(pk)).status_code, 404)
        self.assertEqual(self.client.post(READ_ALL_URL).status_code, 204)
        self.as_user(self.owner_a, self.business_a)
        self.assertEqual(self.client.get(COUNT_URL).data, {"unread": 2})


class ChannelTests(TenantAPITestCase):
    def test_outside_channels_fail_visibly(self):
        with tenant_context(self.business_a):
            for channel in ("EMAIL", "SMS", "WHATSAPP"):
                notification = Notification.objects.create(kind="LOW_STOCK", channel=channel, dedupe_key=channel)
                with self.subTest(channel), self.assertLogs("notifications.channels", "ERROR"):
                    with self.assertRaises(ChannelNotConfigured):
                        deliver(notification, self.owner_a)
            in_app = Notification.objects.create(kind="LOW_STOCK", dedupe_key="in-app")
            deliver(in_app, self.owner_a)  # nothing to send, no error
