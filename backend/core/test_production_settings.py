import os
import subprocess
import sys

from django.test import SimpleTestCase


class ProductionSettingsTests(SimpleTestCase):
    def run_settings(self, code, **overrides):
        environment = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "config.settings_production",
            "DJANGO_SECRET_KEY": "test-only-production-settings-key-" * 3,
            "ALLOWED_HOSTS": "bbmapi.mauzo.tz",
            "CORS_ALLOWED_ORIGINS": "https://bbm.mauzo.tz",
            "CSRF_TRUSTED_ORIGINS": "https://bbmapi.mauzo.tz",
            "FRONTEND_URL": "https://bbm.mauzo.tz",
            "REDIS_URL": "redis://redis:6379/0",
            "EMAIL_HOST": "smtp.example.com",
            "EMAIL_HOST_USER": "test",
            "EMAIL_HOST_PASSWORD": "REPLACE_ME-test-only",
            "EMAIL_USE_TLS": "True",
            "EMAIL_USE_SSL": "False",
            "DEFAULT_FROM_EMAIL": "test@example.com",
            **overrides,
        }
        return subprocess.run(
            [sys.executable, "-c", code],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_production_configuration_and_smtp(self):
        result = self.run_settings("""
import django
django.setup()
from django.conf import settings
from django.core.mail import get_connection
assert settings.DEBUG is False
assert settings.STATIC_URL == "/static/"
assert settings.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
assert settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE
assert settings.SECURE_SSL_REDIRECT
assert settings.REST_FRAMEWORK["NUM_PROXIES"] == 2
assert settings.CORS_ALLOWED_ORIGINS == ["https://bbm.mauzo.tz"]
connection = get_connection()
assert connection.host == "smtp.example.com"
assert connection.use_tls and not connection.use_ssl
""", DEBUG="True")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_production_configuration_fails(self):
        for overrides, message in [
            ({"REDIS_URL": ""}, "REDIS_URL is required"),
            ({"DJANGO_SECRET_KEY": "REPLACE_ME"}, "unique production DJANGO_SECRET_KEY"),
            ({"ALLOWED_HOSTS": "*"}, "Explicit production ALLOWED_HOSTS"),
            ({"EMAIL_USE_SSL": "True"}, "Choose EMAIL_USE_TLS or EMAIL_USE_SSL"),
        ]:
            with self.subTest(overrides=overrides):
                result = self.run_settings(
                    "from django.conf import settings; print(settings.DEBUG)", **overrides
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
