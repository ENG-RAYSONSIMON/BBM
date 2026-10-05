"""NFR-3: auth endpoints are rate limited per client IP."""

from django.core.cache import cache
from django.urls import reverse_lazy
from rest_framework.test import APITestCase

from accounts.services import register_owner
from accounts.tokens import tokens_for

PASSWORD = "Str0ng-Passw0rd!"


class AuthThrottleTests(APITestCase):
    """Uses the default rates from settings: login 10/min, register 5/hour,
    refresh 30/min."""

    def setUp(self):
        cache.clear()
        self.user, self.business = register_owner(
            email="owner@example.com", password=PASSWORD, business_name="Shop A"
        )

    def test_login_is_throttled(self):
        url = reverse_lazy("accounts:login")
        data = {"email": "owner@example.com", "password": "wrong-password"}
        for _ in range(10):
            self.assertEqual(self.client.post(url, data, format="json").status_code, 401)
        self.assertEqual(self.client.post(url, data, format="json").status_code, 429)

    def test_register_is_throttled(self):
        url = reverse_lazy("accounts:register")
        for i in range(5):
            data = {"email": f"new{i}@example.com", "password": PASSWORD, "business_name": "Shop"}
            self.assertEqual(self.client.post(url, data, format="json").status_code, 201)
        data = {"email": "new9@example.com", "password": PASSWORD, "business_name": "Shop"}
        self.assertEqual(self.client.post(url, data, format="json").status_code, 429)

    def test_refresh_is_throttled(self):
        url = reverse_lazy("accounts:refresh")
        for _ in range(30):
            self.client.post(url, {"refresh": "not-a-token"}, format="json")
        response = self.client.post(url, {"refresh": "not-a-token"}, format="json")
        self.assertEqual(response.status_code, 429)

    def test_scopes_are_counted_separately(self):
        login = reverse_lazy("accounts:login")
        data = {"email": "owner@example.com", "password": "wrong-password"}
        for _ in range(10):
            self.client.post(login, data, format="json")
        refresh = tokens_for(self.user, self.business)["refresh"]
        response = self.client.post(
            reverse_lazy("accounts:refresh"), {"refresh": refresh}, format="json"
        )
        self.assertEqual(response.status_code, 200)
