"""Render a secret dotenv plus the two exact image digests from this run."""

import os
from pathlib import Path
import re
import sys

REQUIRED = {
    "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "DJANGO_SECRET_KEY",
    "DATABASE_URL", "REDIS_URL", "ALLOWED_HOSTS", "CORS_ALLOWED_ORIGINS",
    "CSRF_TRUSTED_ORIGINS", "FRONTEND_URL", "EMAIL_HOST", "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD", "DEFAULT_FROM_EMAIL",
}
OPTIONAL = {
    "EMAIL_PORT", "EMAIL_USE_TLS", "EMAIL_USE_SSL", "SECURE_HSTS_SECONDS",
    "PRODUCT_IMAGE_MAX_BYTES", "EXPENSE_RECEIPT_MAX_BYTES",
    "PASSWORD_RESET_TIMEOUT", "LOGIN_THROTTLE_RATE", "REGISTER_THROTTLE_RATE",
    "TOKEN_REFRESH_THROTTLE_RATE", "PASSWORD_RESET_THROTTLE_RATE",
}


def render(content, references):
    seen = set()
    for line in content.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([A-Z_]+)=(.+)", line)
        if not match:
            raise ValueError("Use one NAME=value assignment per line; multiline values are unsupported.")
        key, value = match.groups()
        if key not in REQUIRED | OPTIONAL or key in seen:
            raise ValueError(f"Unexpected or duplicate setting: {key}")
        seen.add(key)
        if "\x00" in value or "\r" in value or "REPLACE_ME" in value:
            raise ValueError(f"Invalid or placeholder value for {key}")
        if value.startswith("'"):
            if not re.fullmatch(r"'(?:[^'\\]|\\.)+'", value):
                raise ValueError(f"Invalid single-quoted value for {key}")
        elif any(character in value for character in "$#'\"") or value != value.strip():
            raise ValueError(f"Use single quotes around special characters in {key}")
    missing = REQUIRED - seen
    if missing:
        raise ValueError("Missing production settings: " + ", ".join(sorted(missing)))
    image_lines = []
    for component in ("backend", "frontend"):
        reference = references[component].strip()
        if not re.fullmatch(rf"ghcr\.io/[a-z0-9._/-]+/bbm-{component}@sha256:[0-9a-f]{{64}}", reference):
            raise ValueError(f"Invalid {component} image digest reference")
        image_lines.append(f"{component.upper()}_IMAGE={reference}")
    return content.rstrip() + "\n" + "\n".join(image_lines) + "\n"


if __name__ == "__main__":
    try:
        directory, output = map(Path, sys.argv[1:])
        result = render(
            os.environ["PRODUCTION_ENV"],
            {component: (directory / f"{component}.txt").read_text() for component in ("backend", "frontend")},
        )
        output.write_text(result)
        output.chmod(0o600)
    except (ValueError, KeyError, OSError) as error:
        sys.exit(str(error))
