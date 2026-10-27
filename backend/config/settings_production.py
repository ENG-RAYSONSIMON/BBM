"""Settings for the image-based deployment behind Traefik and nginx."""

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403
from .settings import env

DEBUG = False
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS")
FRONTEND_URL = env("FRONTEND_URL")

if not env("REDIS_URL", default=""):
    raise ImproperlyConfigured("REDIS_URL is required in production.")
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("REPLACE_ME"):  # noqa: F405
    raise ImproperlyConfigured("Set a unique production DJANGO_SECRET_KEY of at least 50 characters.")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Explicit production ALLOWED_HOSTS are required.")
# Password-reset emails must really go out, with links to the real site.
for name in ("FRONTEND_URL", "EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD", "DEFAULT_FROM_EMAIL"):
    value = env(name, default="").strip()
    if not value or value.startswith("REPLACE_ME"):
        raise ImproperlyConfigured(f"Set {name} in .env (it is empty or still REPLACE_ME).")
if not FRONTEND_URL.startswith("https://"):
    raise ImproperlyConfigured("FRONTEND_URL must be the https:// address of the site.")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# Start with a short policy; increase after confirming HTTPS on the real domain.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Only Traefik -> nginx -> Django may reach the backend.
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": 2}  # noqa: F405

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": env("EMAIL_HOST"),
            "port": env.int("EMAIL_PORT", default=587),
            "username": env("EMAIL_HOST_USER"),
            "password": env("EMAIL_HOST_PASSWORD"),
            "use_tls": env.bool("EMAIL_USE_TLS", default=True),
            "use_ssl": env.bool("EMAIL_USE_SSL", default=False),
            "timeout": 15,
        },
    },
}
if MAILERS["default"]["OPTIONS"]["use_tls"] and MAILERS["default"]["OPTIONS"]["use_ssl"]:
    raise ImproperlyConfigured("Choose EMAIL_USE_TLS or EMAIL_USE_SSL, not both.")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
