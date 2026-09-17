from django.test import TestCase

from accounts.models import Role, User, UserRole
from accounts.services import register_owner

from .tenancy import (
    TenantContextMissing,
    TenantMismatch,
    get_current_business_id,
    tenant_context,
)

PASSWORD = "Str0ng-Passw0rd!"


class TenantScopingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _, cls.business_a = register_owner(
            email="a@example.com", password=PASSWORD, business_name="Shop A"
        )
        _, cls.business_b = register_owner(
            email="b@example.com", password=PASSWORD, business_name="Shop B"
        )
        cls.role_b = Role.all_objects.get(business=cls.business_b, name=Role.OWNER)

    def test_query_without_active_business_fails_closed(self):
        with self.assertRaises(TenantContextMissing):
            list(Role.objects.all())

    def test_only_active_business_rows_are_visible(self):
        with tenant_context(self.business_a):
            self.assertEqual(
                set(Role.objects.values_list("business_id", flat=True)),
                {self.business_a.pk},
            )
            self.assertFalse(Role.objects.filter(pk=self.role_b.pk).exists())

    def test_queryset_built_early_is_scoped_when_executed(self):
        queryset = Role.objects.filter(name=Role.OWNER)
        with tenant_context(self.business_a):
            self.assertEqual(queryset.all().get().business_id, self.business_a.pk)
        with tenant_context(self.business_b):
            self.assertEqual(queryset.all().get().business_id, self.business_b.pk)

    def test_bulk_update_is_scoped(self):
        with tenant_context(self.business_a):
            self.assertEqual(Role.objects.update(is_system=False), 2)  # Owner + Admin
        self.role_b.refresh_from_db()
        self.assertTrue(self.role_b.is_system)

    def test_all_objects_is_unscoped(self):
        self.assertEqual(Role.all_objects.count(), 4)  # Owner + Admin per business

    def test_save_assigns_active_business(self):
        with tenant_context(self.business_a):
            role = Role.objects.create(name="Cashier")
        self.assertEqual(role.business_id, self.business_a.pk)

    def test_save_without_active_business_fails(self):
        with self.assertRaises(TenantContextMissing):
            Role(name="Cashier").save()

    def test_save_into_another_business_is_rejected(self):
        with tenant_context(self.business_a):
            with self.assertRaises(TenantMismatch):
                Role(name="Cashier", business=self.business_b).save()

    def test_user_role_cannot_use_role_from_another_business(self):
        user = User.objects.get(email="a@example.com")
        with tenant_context(self.business_a):
            with self.assertRaises(TenantMismatch):
                UserRole(user=user, role=self.role_b).save()

    def test_context_is_restored_after_block(self):
        with tenant_context(self.business_a):
            with tenant_context(self.business_b):
                self.assertEqual(get_current_business_id(), self.business_b.pk)
            self.assertEqual(get_current_business_id(), self.business_a.pk)
        self.assertIsNone(get_current_business_id())
