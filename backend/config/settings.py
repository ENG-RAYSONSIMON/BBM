"""
Django settings for config project.
"""

import os
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "corsheaders",
    "django_filters",
    "core",
    "accounts",
    "catalog",
    "inventory",
    "sales",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.TenantContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
DATABASES = {
    "default": env.db("DATABASE_URL"),
}


# Cache (throttle counters). Redis is shared by all workers and survives
# restarts; production must set REDIS_URL. Without it, fall back to a
# per-process LocMem cache so manage.py still runs outside Docker.
REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "KEY_PREFIX": "bbm",
        },
    }
else:
    CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    }


# Password validation + hashing
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "accounts.User"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]


# DRF / JWT / OpenAPI
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "core.authentication.TenantJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
        "core.permissions.HasTenantPermission",
    ),
    "DEFAULT_SCHEMA_CLASS": "core.schema.TenantAutoSchema",
    "DEFAULT_PAGINATION_CLASS": "core.pagination.DefaultPagination",
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    # NFR-3. Counters are per client IP and live in CACHES["default"]. Once
    # nginx sits in front, set NUM_PROXIES so the real client IP is used
    # instead of the proxy's.
    "DEFAULT_THROTTLE_RATES": {
        "password_reset": env("PASSWORD_RESET_THROTTLE_RATE", default="5/hour"),
        "register": env("REGISTER_THROTTLE_RATE", default="5/hour"),
        "login": env("LOGIN_THROTTLE_RATE", default="10/min"),
        "token_refresh": env("TOKEN_REFRESH_THROTTLE_RATE", default="30/min"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=20),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Beauty Business Manager API",
    "DESCRIPTION": "Multi-tenant SaaS API for beauty and cosmetics retailers.",
    "VERSION": "0.1.0",
    # Docs are only routed when DEBUG is on (config/urls.py).
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SERVE_AUTHENTICATION": [],
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "TAGS": [
        {"name": "auth", "description": "Registration, login, token rotation, current user."},
        {"name": "password reset", "description": "FR-4 single-use, time-limited reset tokens."},
        {"name": "settings", "description": "Per-business configuration."},
        {"name": "catalog", "description": "Products, categories, brands and suppliers."},
        {"name": "inventory", "description": "Batches, the stock ledger and stock alerts."},
    ],
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": True},
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])


# Internationalization
LANGUAGE_CODE = "en-us"
# Tanzania (EAT). Datetimes are stored in UTC; this sets what "today" means,
# e.g. for expiry windows.
TIME_ZONE = "Africa/Dar_es_Salaam"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

# Uploaded files (product images). Not under any static/web root; Django
# serves them only when DEBUG. Production moves to object storage via STORAGES.
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
PRODUCT_IMAGE_MAX_BYTES = env.int("PRODUCT_IMAGE_MAX_BYTES", default=2 * 1024 * 1024)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.console.EmailBackend",
        # When switching to SMTP, read credentials from env with REPLACE_ME
        # placeholders in .env, never literal values here.
    },
}
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@bbm.local")

# FR-4 password reset
PASSWORD_RESET_TIMEOUT = env.int("PASSWORD_RESET_TIMEOUT", default=30 * 60)  # seconds
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:5173")