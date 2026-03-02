"""Django settings for Person Validator."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

# Build paths relative to project root (person-validator/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent


def _load_env_file():
    """Load key=value pairs from the project env file into os.environ.

    Uses ``os.environ.setdefault`` so explicit env vars always win.
    Runs once at import time — acceptable trade-off because pytest-django
    isolates Django settings via its ``settings`` fixture, and real env
    vars (e.g. in CI) take precedence over file values.
    """
    env_path = BASE_DIR / "env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                value = value.strip()
                # Strip surrounding quotes (single or double)
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                os.environ.setdefault(key.strip(), value)


_load_env_file()

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is not set. Add it to the project 'env' file.")

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "person-validator.exe.xyz",
    ".exe.xyz",
]

CSRF_TRUSTED_ORIGINS = [
    "https://person-validator.exe.xyz",
    "https://person-validator.exe.xyz:8000",
]

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "src.web.accounts",
    "src.web.persons",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "src.web.accounts.middleware.ExeDevEmailAuthMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "src.web.config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "src.web.config.wsgi.application"

# Database — single shared SQLite at project root
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTHENTICATION_BACKENDS = [
    "src.web.accounts.backends.ExeDevEmailBackend",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Internationalization & time zones
TIME_ZONE = "UTC"
USE_TZ = True

# exe.dev proxy settings
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# Superuser bootstrap email priority:
# 1. ADMIN_DEV_EMAIL from env file
# 2. Email from ~/.config/shelley/AGENTS.md
# At runtime, the matching X-ExeDev-Email header triggers promotion.
ADMIN_DEV_EMAIL = os.environ.get("ADMIN_DEV_EMAIL", "")
if not ADMIN_DEV_EMAIL:
    # Fall back to shelley config before giving up
    try:
        _shelley_agents = Path.home() / ".config" / "shelley" / "AGENTS.md"
        if _shelley_agents.exists():
            import re as _re

            _match = _re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", _shelley_agents.read_text())
            if _match:
                ADMIN_DEV_EMAIL = _match.group(0)
    except Exception:
        pass

if not ADMIN_DEV_EMAIL:
    raise ImproperlyConfigured(
        "ADMIN_DEV_EMAIL is not set and could not be detected from "
        "~/.config/shelley/AGENTS.md. Add it to the project 'env' file."
    )
