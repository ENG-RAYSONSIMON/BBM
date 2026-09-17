import hashlib
import re
from datetime import timedelta

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse_lazy
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import PasswordResetToken
from accounts.services import register_owner

PASSWORD = "Str0ng-Passw0rd!"
NEW_PASSWORD = "An0ther-Str0ng-One!"


class PasswordResetTests(APITestCase):
    request_url = reverse_lazy("accounts:password-reset")
    confirm_url = reverse_lazy("accounts:password-reset-confirm")

    def setUp(self):
        cache.clear()  # throttle counters live in the cache
        self.user, self.business = register_owner(
            email="owner@example.com", password=PASSWORD, business_name="Shop A"
        )

    def request_reset(self, email="owner@example.com"):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.request_url, {"email": email}, format="json")

    def raw_token_from_last_email(self):
        return re.search(r"#token=(\S+)", mail.outbox[-1].body).group(1)

    def confirm(self, token, password=NEW_PASSWORD):
        return self.client.post(
            self.confirm_url, {"token": token, "new_password": password}, format="json"
        )

    def login(self, password):
        return self.client.post(
            reverse_lazy("accounts:login"),
            {"email": "owner@example.com", "password": password},
            format="json",
        )

    def test_response_does_not_reveal_account_existence(self):
        known = self.request_reset("OWNER@example.com")
        unknown = self.request_reset("nobody@example.com")

        self.assertEqual(known.status_code, 202)
        self.assertEqual((known.status_code, known.data), (unknown.status_code, unknown.data))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["owner@example.com"])

    def test_inactive_user_gets_no_email(self):
        self.user.is_active = False
        self.user.save()

        self.assertEqual(self.request_reset().status_code, 202)
        self.assertEqual(len(mail.outbox), 0)

    def test_only_the_hash_is_stored(self):
        self.request_reset()
        raw = self.raw_token_from_last_email()

        token = PasswordResetToken.objects.get()
        self.assertNotEqual(token.token_hash, raw)
        self.assertEqual(token.token_hash, hashlib.sha256(raw.encode()).hexdigest())

    def test_token_is_single_use(self):
        self.request_reset()
        raw = self.raw_token_from_last_email()

        self.assertEqual(self.confirm(raw).status_code, 204)
        second = self.confirm(raw, password="Yet-An0ther-Pass!")
        self.assertEqual(second.status_code, 400)
        self.assertIn("token", second.data)
        self.assertEqual(self.login(NEW_PASSWORD).status_code, 200)

    def test_expired_token_is_rejected_with_the_same_error(self):
        self.request_reset()
        raw = self.raw_token_from_last_email()
        PasswordResetToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

        expired = self.confirm(raw)
        garbage = self.confirm("not-a-real-token")
        self.assertEqual(expired.status_code, 400)
        self.assertEqual(expired.data, garbage.data)
        self.assertEqual(self.login(PASSWORD).status_code, 200)

    @override_settings(PASSWORD_RESET_TIMEOUT=600)
    def test_expiry_follows_setting(self):
        self.request_reset()
        token = PasswordResetToken.objects.get()
        self.assertAlmostEqual(
            (token.expires_at - token.created_at).total_seconds(), 600, delta=5
        )

    def test_newer_request_revokes_older_token(self):
        self.request_reset()
        old = self.raw_token_from_last_email()
        self.request_reset()
        new = self.raw_token_from_last_email()

        self.assertEqual(self.confirm(old).status_code, 400)
        self.assertEqual(self.confirm(new).status_code, 204)

    def test_weak_password_keeps_token_usable(self):
        self.request_reset()
        raw = self.raw_token_from_last_email()

        weak = self.confirm(raw, password="password")
        self.assertEqual(weak.status_code, 400)
        self.assertIn("new_password", weak.data)
        self.assertIsNone(PasswordResetToken.objects.get().used_at)
        self.assertEqual(self.confirm(raw).status_code, 204)

    def test_reset_revokes_existing_refresh_tokens(self):
        refresh = self.login(PASSWORD).data["refresh"]
        self.request_reset()

        self.assertEqual(self.confirm(self.raw_token_from_last_email()).status_code, 204)
        response = self.client.post(
            reverse_lazy("accounts:refresh"), {"refresh": refresh}, format="json"
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.login(PASSWORD).status_code, 401)

    def test_requests_are_throttled(self):
        for _ in range(5):
            self.assertEqual(self.request_reset("nobody@example.com").status_code, 202)
        self.assertEqual(self.request_reset("nobody@example.com").status_code, 429)
