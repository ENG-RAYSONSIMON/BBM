from unittest import mock

from django.test import TestCase
from django.urls import reverse_lazy
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import Business, BusinessSettings, Role, RolePermission, User, UserRole
from accounts.services import register_owner
from core.tenancy import tenant_context

PAYLOAD = {
    "email": "owner@example.com",
    "password": "Str0ng-Passw0rd!",
    "first_name": "Amina",
    "last_name": "Juma",
    "business_name": "Glow Cosmetics",
}


class RegisterEndpointTests(APITestCase):
    url = reverse_lazy("accounts:register")

    def test_creates_user_business_owner_role_and_settings(self):
        response = self.client.post(self.url, PAYLOAD, format="json")

        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get()
        business = Business.objects.get()
        self.assertEqual(business.name, "Glow Cosmetics")
        self.assertEqual(business.currency, "TZS")
        self.assertTrue(user.password.startswith("argon2"))
        with tenant_context(business):
            role = Role.objects.get(name=Role.OWNER)
            membership = UserRole.objects.get()
            self.assertTrue(BusinessSettings.objects.exists())
        self.assertEqual((role.name, role.is_system), (Role.OWNER, True))
        self.assertEqual((membership.user, membership.role), (user, role))

        self.assertEqual(response.data["business"]["id"], str(business.pk))
        self.assertEqual(response.data["role"], Role.OWNER)
        self.assertEqual(AccessToken(response.data["access"])["business_id"], str(business.pk))
        self.assertIn("refresh", response.data)

    def test_duplicate_email_is_rejected_case_insensitively(self):
        self.client.post(self.url, PAYLOAD, format="json")
        response = self.client.post(
            self.url, {**PAYLOAD, "email": "OWNER@Example.com"}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)
        self.assertEqual(User.objects.count(), 1)

    def test_weak_password_is_rejected(self):
        response = self.client.post(self.url, {**PAYLOAD, "password": "password"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)
        self.assertFalse(User.objects.exists())


class RegisterOwnerTransactionTests(TestCase):
    def test_failure_on_last_step_rolls_back_everything(self):
        with mock.patch.object(BusinessSettings, "save", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                register_owner(
                    email="owner@example.com",
                    password="Str0ng-Passw0rd!",
                    business_name="Glow Cosmetics",
                )

        self.assertFalse(User.objects.exists())
        self.assertFalse(Business.objects.exists())
        self.assertFalse(Role.all_objects.exists())
        self.assertFalse(RolePermission.all_objects.exists())
        self.assertFalse(UserRole.all_objects.exists())
        self.assertFalse(BusinessSettings.all_objects.exists())
