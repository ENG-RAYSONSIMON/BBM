from django.urls import reverse_lazy
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import Role, UserRole
from accounts.services import register_owner
from accounts.tokens import tokens_for
from core.tenancy import get_current_business_id, tenant_context

PASSWORD = "Str0ng-Passw0rd!"


def make_owner(email, business_name):
    return register_owner(email=email, password=PASSWORD, business_name=business_name)


class LoginTests(APITestCase):
    url = reverse_lazy("accounts:login")

    def setUp(self):
        self.user, self.business = make_owner("owner@example.com", "Shop A")

    def login(self, **overrides):
        data = {"email": "owner@example.com", "password": PASSWORD, **overrides}
        return self.client.post(self.url, data, format="json")

    def test_bad_credentials_give_the_same_401(self):
        wrong_password = self.login(password="not-the-password")
        unknown_email = self.login(email="nobody@example.com")

        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(unknown_email.status_code, 401)
        self.assertEqual(wrong_password.data["detail"], unknown_email.data["detail"])

    def test_single_membership_is_selected_automatically(self):
        response = self.login(email="OWNER@example.com")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(AccessToken(response.data["access"])["business_id"], str(self.business.pk))
        self.assertEqual(response.data["role"], Role.OWNER)

    def test_several_memberships_require_a_business_choice(self):
        _, other = make_owner("other@example.com", "Shop B")
        with tenant_context(other):
            UserRole.objects.create(user=self.user, role=Role.objects.get(name=Role.ADMIN))

        unchosen = self.login()
        self.assertEqual(unchosen.status_code, 400)
        self.assertIn("business_id", unchosen.data)
        self.assertEqual(len(unchosen.data["businesses"]), 2)

        chosen = self.login(business_id=str(other.pk))
        self.assertEqual(chosen.status_code, 200, chosen.data)
        self.assertEqual(AccessToken(chosen.data["access"])["business_id"], str(other.pk))
        self.assertEqual(chosen.data["role"], "Admin")

    def test_business_the_user_does_not_belong_to_is_rejected(self):
        _, other = make_owner("other@example.com", "Shop B")

        response = self.login(business_id=str(other.pk))

        self.assertEqual(response.status_code, 400)


class RefreshTests(APITestCase):
    url = reverse_lazy("accounts:refresh")

    def setUp(self):
        self.user, self.business = make_owner("owner@example.com", "Shop A")
        self.refresh = tokens_for(self.user, self.business)["refresh"]

    def test_refresh_rotates_and_the_old_token_is_rejected(self):
        response = self.client.post(self.url, {"refresh": self.refresh}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotEqual(response.data["refresh"], self.refresh)
        self.assertEqual(AccessToken(response.data["access"])["business_id"], str(self.business.pk))

        reused = self.client.post(self.url, {"refresh": self.refresh}, format="json")
        self.assertEqual(reused.status_code, 401)

    def test_refresh_is_rejected_once_membership_is_deactivated(self):
        UserRole.all_objects.filter(user=self.user).update(is_active=False)

        response = self.client.post(self.url, {"refresh": self.refresh}, format="json")

        self.assertEqual(response.status_code, 401)


class TenantAuthenticationTests(APITestCase):
    me_url = reverse_lazy("accounts:me")

    def setUp(self):
        self.user_a, self.business_a = make_owner("a@example.com", "Shop A")
        self.user_b, self.business_b = make_owner("b@example.com", "Shop B")

    def authenticate(self, user, business):
        tokens = tokens_for(user, business)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        return tokens

    def test_me_reports_the_business_from_the_token(self):
        self.authenticate(self.user_a, self.business_a)

        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["business"]["id"], str(self.business_a.pk))
        self.assertEqual(response.data["role"], Role.OWNER)
        self.assertIsNone(get_current_business_id(), "tenant leaked past the request")

    def test_token_for_a_business_without_membership_is_rejected(self):
        self.authenticate(self.user_a, self.business_b)

        self.assertEqual(self.client.get(self.me_url).status_code, 401)

    def test_access_token_is_rejected_once_membership_is_deactivated(self):
        self.authenticate(self.user_a, self.business_a)
        UserRole.all_objects.filter(user=self.user_a).update(is_active=False)

        self.assertEqual(self.client.get(self.me_url).status_code, 401)

    def test_logout_blacklists_the_refresh_token(self):
        tokens = self.authenticate(self.user_a, self.business_a)

        response = self.client.post(
            reverse_lazy("accounts:logout"), {"refresh": tokens["refresh"]}, format="json"
        )
        self.assertEqual(response.status_code, 204)

        self.client.credentials()
        refreshed = self.client.post(
            reverse_lazy("accounts:refresh"), {"refresh": tokens["refresh"]}, format="json"
        )
        self.assertEqual(refreshed.status_code, 401)
