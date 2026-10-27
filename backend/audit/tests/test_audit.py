"""FR-20: sensitive actions are logged in the same transaction, entries are
append-only, and only the Owner can read them."""

from django.db import DatabaseError, connection, transaction
from django.urls import reverse

from accounts.models import Role, User, UserRole
from audit.models import AuditLog, AuditLogImmutable
from catalog.models import Category
from catalog.tests.helpers import PASSWORD, TenantAPITestCase, make_product, stock
from core.tenancy import tenant_context
from expenses.models import ExpenseCategory
from purchases.tests.helpers import PurchasesAPITestCase, cancel_url
from sales.tests.helpers import SalesAPITestCase

LOGS_URL = reverse("audit:audit-log-list")
SETTINGS_URL = "/api/v1/settings/"


def entries(business, **filters):
    return list(AuditLog.all_objects.filter(business=business, **filters))


class DeleteAuditTests(TenantAPITestCase):
    def setUp(self):
        super().setUp()
        self.as_user(self.owner_a, self.business_a)

    def test_delete_is_logged_with_actor_label_and_ip(self):
        with tenant_context(self.business_a):
            category = Category.objects.create(name="Lotions")
        url = reverse("catalog:category-detail", args=[category.pk])
        self.assertEqual(self.client.delete(url).status_code, 204)

        [entry] = entries(self.business_a)
        self.assertEqual(entry.action, AuditLog.Action.DELETE)
        self.assertEqual(entry.actor, self.owner_a)
        self.assertEqual((entry.target_type, entry.target_id, entry.target_label), ("category", category.pk, "Lotions"))
        self.assertEqual(entry.ip_address, "127.0.0.1")

    def test_refused_delete_leaves_no_entry(self):
        with tenant_context(self.business_a):
            category = Category.objects.create(name="Lotions")
        make_product(self.business_a, category=category)
        url = reverse("catalog:category-detail", args=[category.pk])
        self.assertEqual(self.client.delete(url).status_code, 409)
        self.assertEqual(entries(self.business_a), [])

    def test_product_delete_is_logged_but_not_a_refused_one(self):
        empty = make_product(self.business_a, "Rose Water")
        stocked = make_product(self.business_a, "Shea Butter")
        stock(self.business_a, stocked, 3, self.owner_a)
        self.assertEqual(self.client.delete(reverse("catalog:product-detail", args=[stocked.pk])).status_code, 409)
        self.assertEqual(self.client.delete(reverse("catalog:product-detail", args=[empty.pk])).status_code, 204)
        self.assertEqual([e.target_label for e in entries(self.business_a)], ["Rose Water"])


class DiffTests(TenantAPITestCase):
    def test_related_rows_compare_by_pk_not_by_name(self):
        from audit.services import diff

        with tenant_context(self.business_a):
            first = Category.objects.create(name="Lotions")
            second = Category.objects.create(name="Creams")
        second.name = "Lotions"  # names are unique per business, so make them print alike in memory
        product = make_product(self.business_a, category=first)
        self.assertEqual(diff(product, {"category": second}), {"category": ["Lotions", "Lotions"]})
        self.assertEqual(diff(product, {"category": first}), {})


class ExpenseAndSettingsAuditTests(TenantAPITestCase):
    def setUp(self):
        super().setUp()
        self.as_user(self.owner_a, self.business_a)
        with tenant_context(self.business_a):
            self.rent = ExpenseCategory.objects.get(name="Rent")

    def test_expense_edit_logs_only_changed_fields_and_delete_is_logged(self):
        created = self.client.post(
            reverse("expenses:expense-list"),
            {"category": str(self.rent.pk), "amount": "50000", "description": "October rent"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        url = reverse("expenses:expense-detail", args=[created.data["id"]])
        self.assertEqual(self.client.patch(url, {"amount": "50000"}, format="json").status_code, 200)
        self.assertEqual(entries(self.business_a), [])  # nothing changed

        self.client.patch(url, {"amount": "55000"}, format="json")
        [edit] = entries(self.business_a)
        self.assertEqual(edit.action, AuditLog.Action.EXPENSE_CHANGE)
        self.assertEqual(edit.changes, {"amount": ["50000.00", "55000.00"]})

        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(entries(self.business_a, action=AuditLog.Action.DELETE)[0].target_type, "expense")

    def test_settings_change_is_logged(self):
        response = self.client.patch(SETTINGS_URL, {"low_stock_threshold": 9}, format="json")
        self.assertEqual(response.status_code, 200)
        [entry] = entries(self.business_a)
        self.assertEqual(entry.action, AuditLog.Action.SETTINGS_CHANGE)
        self.assertEqual(entry.changes, {"low_stock_threshold": [5, 9]})
        self.assertEqual(entry.target_label, "")


class VoidAuditTests(SalesAPITestCase):
    def test_void_is_logged(self):
        sale = self.sell().data
        response = self.client.post(reverse("sales:sale-void", args=[sale["id"]]), {"reason": "Wrong item"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        [entry] = entries(self.business_a)
        self.assertEqual(entry.action, AuditLog.Action.SALE_VOID)
        self.assertEqual(entry.target_label, sale["receipt_number"])
        self.assertEqual(entry.changes, {"reason": "Wrong item", "refunded": "12000.00"})

    def test_refused_void_leaves_no_entry(self):
        sale = self.sell().data
        url = reverse("sales:sale-void", args=[sale["id"]])
        self.client.post(url, {"reason": "Wrong item"}, format="json")
        self.assertEqual(self.client.post(url, {"reason": "Again"}, format="json").status_code, 400)
        self.assertEqual(len(entries(self.business_a)), 1)


class CancelAuditTests(PurchasesAPITestCase):
    def test_cancel_is_logged(self):
        purchase = self.draft().data
        response = self.client.post(cancel_url(purchase["id"]), {"reason": "Ordered twice"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        [entry] = entries(self.business_a)
        self.assertEqual(entry.action, AuditLog.Action.PURCHASE_CANCEL)
        self.assertEqual(entry.changes, {"reason": "Ordered twice"})


class RoleChangeAuditTests(TenantAPITestCase):
    def test_admin_site_membership_change_is_logged(self):
        superuser = User.objects.create_superuser(email="root@example.com", password=PASSWORD)
        self.client.force_login(superuser)
        with tenant_context(self.business_a):
            membership = UserRole.objects.get(user=self.admin_a)
        url = reverse("admin:accounts_userrole_change", args=[membership.pk])
        response = self.client.post(url, {"user": self.admin_a.pk, "role": membership.role_id})  # is_active unticked
        self.assertEqual(response.status_code, 302)

        [entry] = entries(self.business_a)
        self.assertEqual(entry.action, AuditLog.Action.ROLE_CHANGE)
        self.assertEqual(entry.actor, superuser)
        self.assertEqual(entry.changes, {"is_active": [True, False]})


class ImmutabilityTests(TenantAPITestCase):
    def test_entries_cannot_be_changed_or_deleted(self):
        with tenant_context(self.business_a):
            entry = AuditLog.objects.create(action=AuditLog.Action.EXPORT)
            entry.target_label = "edited"
            with self.assertRaises(AuditLogImmutable):
                entry.save()
            # Deletes run in their own atomic block; a savepoint keeps the
            # test transaction usable after each refusal.
            with self.assertRaises(AuditLogImmutable), transaction.atomic():
                entry.delete()
            with self.assertRaises(AuditLogImmutable), transaction.atomic():
                AuditLog.objects.all().delete()
            for manager in (AuditLog.objects, AuditLog.all_objects):
                with self.assertRaises(AuditLogImmutable):
                    manager.update(target_label="edited")
                with self.assertRaises(AuditLogImmutable):
                    manager.bulk_update([entry], ["target_label"])
            self.assertEqual(AuditLog.objects.get().target_label, "")

    def test_raw_sql_cannot_change_or_delete_entries(self):
        # The database trigger is the last line: it holds even past the ORM.
        with tenant_context(self.business_a):
            entry = AuditLog.objects.create(action=AuditLog.Action.EXPORT)
        for sql in (
            "UPDATE audit_auditlog SET target_label = 'edited' WHERE id = %s",
            "DELETE FROM audit_auditlog WHERE id = %s",
        ):
            with self.subTest(sql), self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql, [entry.pk])
        with tenant_context(self.business_a):
            self.assertEqual(AuditLog.objects.get().target_label, "")


class AuditLogAPITests(TenantAPITestCase):
    def setUp(self):
        super().setUp()
        with tenant_context(self.business_a):
            AuditLog.objects.create(action=AuditLog.Action.DELETE, actor=self.owner_a, target_label="Lotions")
            AuditLog.objects.create(action=AuditLog.Action.EXPORT, actor=self.admin_a)
        self.as_user(self.owner_a, self.business_a)

    def test_owner_lists_and_filters(self):
        response = self.client.get(LOGS_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["results"][0]["action"], "EXPORT")  # newest first
        self.assertEqual(response.data["results"][1]["actor_name"], "a@example.com")
        self.assertEqual(self.client.get(LOGS_URL, {"action": "DELETE"}).data["count"], 1)
        self.assertEqual(self.client.get(LOGS_URL, {"actor": str(self.admin_a.pk)}).data["count"], 1)
        self.assertEqual(self.client.get(LOGS_URL, {"search": "lotion"}).data["count"], 1)

    def test_read_only(self):
        entry_id = self.client.get(LOGS_URL).data["results"][0]["id"]
        detail = reverse("audit:audit-log-detail", args=[entry_id])
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual(self.client.post(LOGS_URL, {"action": "DELETE"}, format="json").status_code, 405)
        self.assertEqual(self.client.patch(detail, {"target_label": "x"}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(detail).status_code, 405)

    def test_admin_is_refused(self):
        self.as_user(self.admin_a, self.business_a)
        self.assertEqual(self.client.get(LOGS_URL).status_code, 403)

    def test_other_business_sees_nothing(self):
        entry_id = self.client.get(LOGS_URL).data["results"][0]["id"]
        self.as_user(self.owner_b, self.business_b)
        self.assertEqual(self.client.get(LOGS_URL).data["count"], 0)
        self.assertEqual(self.client.get(reverse("audit:audit-log-detail", args=[entry_id])).status_code, 404)


class NewBusinessGrantTests(TenantAPITestCase):
    def test_new_owner_role_holds_audit_view_and_admin_does_not(self):
        with tenant_context(self.business_b):
            owner = Role.objects.get(name=Role.OWNER)
            admin, _ = Role.objects.get_or_create(name=Role.ADMIN)
            self.assertTrue(owner.grants.filter(permission__codename="audit.view").exists())
            self.assertFalse(admin.grants.filter(permission__codename="audit.view").exists())
