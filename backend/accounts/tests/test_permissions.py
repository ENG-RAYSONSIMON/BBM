from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.urls import reverse_lazy
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate
from rest_framework.views import APIView

from accounts.models import (
    Business,
    BusinessSettings,
    Permission,
    ProtectedRoleError,
    Role,
    RolePermission,
    User,
    UserRole,
)
from accounts.rbac import DEFAULT_ROLE_PERMISSIONS, PERMISSIONS, SETTINGS_MANAGE, SETTINGS_VIEW
from accounts.services import register_owner
from accounts.tokens import tokens_for
from core.permissions import HasTenantPermission
from core.tenancy import TenantMismatch, tenant_context

PASSWORD = "Str0ng-Passw0rd!"


class PermissionTests(APITestCase):
    settings_url = reverse_lazy("accounts:settings")

    def setUp(self):
        self.owner, self.business = register_owner(
            email="owner@example.com", password=PASSWORD, business_name="Shop A"
        )
        self.admin = User.objects.create_user(email="admin@example.com", password=PASSWORD)
        with tenant_context(self.business):
            self.admin_role = Role.objects.get(name=Role.ADMIN)
            UserRole.objects.create(user=self.admin, role=self.admin_role)

    def as_user(self, user, business=None):
        access = tokens_for(user, business or self.business)["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def patch_settings(self, **data):
        return self.client.patch(self.settings_url, data or {"low_stock_threshold": 9}, format="json")

    def grant(self, role, codename):
        with tenant_context(self.business):
            RolePermission.objects.create(
                role=role, permission=Permission.objects.get(codename=codename)
            )

    def test_registration_seeds_default_grants(self):
        with tenant_context(self.business):
            grants = {
                name: set(
                    RolePermission.objects.filter(role__name=name).values_list(
                        "permission__codename", flat=True
                    )
                )
                for name in (Role.OWNER, Role.ADMIN)
            }
        self.assertEqual(grants[Role.OWNER], set(PERMISSIONS))
        self.assertEqual(grants[Role.ADMIN], set(DEFAULT_ROLE_PERMISSIONS[Role.ADMIN]))
        self.assertNotIn(SETTINGS_MANAGE, grants[Role.ADMIN])

    def test_owner_can_view_and_change_settings(self):
        self.as_user(self.owner)

        self.assertEqual(self.client.get(self.settings_url).status_code, 200)
        response = self.patch_settings(low_stock_threshold=12, tax_rate="18.00")
        self.assertEqual(response.status_code, 200, response.data)
        with tenant_context(self.business):
            settings = BusinessSettings.objects.get()
        self.assertEqual(settings.low_stock_threshold, 12)

    def test_admin_can_view_but_not_change_settings(self):
        self.as_user(self.admin)

        self.assertEqual(self.client.get(self.settings_url).status_code, 200)
        self.assertEqual(self.patch_settings().status_code, 403)

    def test_access_follows_table_rows_not_role_names(self):
        self.as_user(self.admin)
        self.grant(self.admin_role, SETTINGS_MANAGE)
        self.assertEqual(self.patch_settings().status_code, 200)

        with tenant_context(self.business):
            RolePermission.objects.filter(role=self.admin_role).delete()
        self.assertEqual(self.client.get(self.settings_url).status_code, 403)

    def test_new_role_needs_no_code_change(self):
        cashier = User.objects.create_user(email="cashier@example.com", password=PASSWORD)
        with tenant_context(self.business):
            role = Role.objects.create(name="Helper")
            UserRole.objects.create(user=cashier, role=role)
        self.as_user(cashier)

        self.assertEqual(self.client.get(self.settings_url).status_code, 403)
        self.grant(role, SETTINGS_VIEW)
        self.assertEqual(self.client.get(self.settings_url).status_code, 200)

    def test_settings_are_those_of_the_token_business(self):
        other_owner, other = register_owner(
            email="other@example.com", password=PASSWORD, business_name="Shop B"
        )
        self.as_user(other_owner, other)

        self.assertEqual(self.patch_settings(low_stock_threshold=99).status_code, 200)
        with tenant_context(self.business):
            self.assertEqual(BusinessSettings.objects.get().low_stock_threshold, 5)
        with tenant_context(other):
            self.assertEqual(BusinessSettings.objects.get().low_stock_threshold, 99)

    def test_client_supplied_business_and_role_are_ignored(self):
        _, other = register_owner(
            email="other@example.com", password=PASSWORD, business_name="Shop B"
        )
        self.as_user(self.admin)
        response = self.client.patch(
            self.settings_url,
            {"low_stock_threshold": 7, "business": str(other.pk), "role": Role.OWNER},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

        self.as_user(self.owner)
        response = self.client.patch(
            self.settings_url,
            {"low_stock_threshold": 7, "business": str(other.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        with tenant_context(other):
            self.assertEqual(BusinessSettings.objects.get().low_stock_threshold, 5)
        with tenant_context(self.business):
            self.assertEqual(BusinessSettings.objects.get().low_stock_threshold, 7)

    def test_invalid_tax_rate_rejected(self):
        self.as_user(self.owner)
        self.assertEqual(self.patch_settings(tax_rate="150").status_code, 400)

    def test_grant_cannot_use_role_from_another_business(self):
        _, other = register_owner(
            email="other@example.com", password=PASSWORD, business_name="Shop B"
        )
        with tenant_context(other):
            other_role = Role.objects.get(name=Role.ADMIN)
        with tenant_context(self.business):
            with self.assertRaises(TenantMismatch):
                RolePermission(
                    role=other_role, permission=Permission.objects.get(codename=SETTINGS_MANAGE)
                ).save()

    def test_me_lists_permissions(self):
        self.as_user(self.admin)
        response = self.client.get(reverse_lazy("accounts:me"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["permissions"], sorted(DEFAULT_ROLE_PERMISSIONS[Role.ADMIN]))

    def test_unauthenticated_settings_request_is_401(self):
        self.assertEqual(self.client.get(self.settings_url).status_code, 401)

    def test_system_roles_cannot_be_renamed_or_unmarked(self):
        with tenant_context(self.business):
            owner_role = Role.objects.get(name=Role.OWNER)
            owner_role.name = "Boss"
            with self.assertRaises(ProtectedRoleError):
                owner_role.save()

            owner_role.refresh_from_db()
            owner_role.is_system = False
            with self.assertRaises(ProtectedRoleError):
                owner_role.save()

    # Deletes send pre_delete inside atomic(savepoint=False), so each expected
    # failure gets its own savepoint to keep the test transaction usable.

    def test_system_roles_cannot_be_deleted(self):
        with tenant_context(self.business):
            UserRole.objects.all().delete()  # memberships PROTECT their role
            with self.assertRaises(ProtectedRoleError), transaction.atomic():
                self.admin_role.delete()
            with self.assertRaises(ProtectedRoleError), transaction.atomic():
                Role.objects.filter(is_system=True).delete()
            self.assertEqual(Role.objects.filter(is_system=True).count(), 4)

    def test_owner_grants_cannot_be_removed(self):
        with tenant_context(self.business):
            grants = RolePermission.objects.filter(role__name=Role.OWNER)
            with self.assertRaises(ProtectedRoleError), transaction.atomic():
                grants.first().delete()
            with self.assertRaises(ProtectedRoleError), transaction.atomic():
                grants.delete()
            self.assertEqual(grants.count(), len(PERMISSIONS))

    def test_custom_roles_can_be_renamed_and_deleted(self):
        with tenant_context(self.business):
            role = Role.objects.create(name="Helper")
            self.grant(role, SETTINGS_VIEW)
            role.name = "Till"
            role.save()
            role.delete()
            self.assertFalse(Role.objects.filter(name__in=["Helper", "Till"]).exists())


class UndeclaredView(APIView):
    permission_classes = (HasTenantPermission,)

    def get(self, request):
        return Response()


class HasTenantPermissionConfigTests(APITestCase):
    def test_view_without_declaration_is_a_programming_error(self):
        request = APIRequestFactory().get("/")
        force_authenticate(request, user=User(email="x@example.com"))
        with self.assertRaises(ImproperlyConfigured):
            UndeclaredView.as_view()(request)


class StaffRolesMigrationTests(APITestCase):
    """0009 gives businesses that existed before it the Seller and Cashier
    roles and the new Owner/Admin grants, and leaves a same-named custom role alone."""

    def test_seeds_roles_for_existing_businesses(self):
        from importlib import import_module

        from django.apps import apps

        migration = import_module("accounts.migrations.0009_staff_roles_permissions")
        business = Business.objects.create(name="Old Shop")
        with tenant_context(business):
            Role.objects.create(name=Role.OWNER, is_system=True)
            Role.objects.create(name=Role.SELLER)  # the shop's own, no grants
            migration.seed(apps, None)
            grants = {
                role.name: set(role.grants.values_list("permission__codename", flat=True))
                for role in Role.objects.all()
            }
            seller = Role.objects.get(name=Role.SELLER)
        self.assertEqual(grants[Role.CASHIER], set(migration.NEW_ROLES[Role.CASHIER]))
        self.assertEqual(grants[Role.OWNER], set(migration.NEW))
        self.assertFalse(seller.is_system)
        self.assertEqual(grants[Role.SELLER], set())


class CashierMigrationTests(APITestCase):
    """0011 gives existing system Cashier roles the money-path grants and
    leaves a business's own role named Cashier alone."""

    def test_grants_existing_cashiers(self):
        from importlib import import_module

        from django.apps import apps

        migration = import_module("accounts.migrations.0011_cashier_runs_the_shop")
        system = Business.objects.create(name="Old Shop")
        custom = Business.objects.create(name="Own Roles Shop")
        with tenant_context(system):
            old_cashier = Role.objects.create(name=Role.CASHIER, is_system=True)
        with tenant_context(custom):
            own_cashier = Role.objects.create(name=Role.CASHIER)
        # The live models' managers are tenant-scoped, so run it per business.
        for business in (system, custom):
            with tenant_context(business):
                migration.grant(apps, None)

        def codenames(role):
            return set(RolePermission.all_objects.filter(role=role).values_list("permission__codename", flat=True))

        self.assertEqual(codenames(old_cashier), set(migration.NEW))
        self.assertEqual(codenames(own_cashier), set())
        self.assertLess(set(DEFAULT_ROLE_PERMISSIONS[Role.CASHIER]), set(DEFAULT_ROLE_PERMISSIONS[Role.ADMIN]))
