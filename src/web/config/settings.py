"""Django settings for Person Validator."""

import logging
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# Build paths relative to project root (person-validator/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Load the project env file. Existing env vars (e.g. from systemd
# EnvironmentFile) take precedence — load_dotenv does not override.
load_dotenv(BASE_DIR / "env")

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
    "src.web.keys",
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

# Logging — JSON to console, level from LOG_LEVEL env var (default INFO)
_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

from pythonjsonlogger import json as _jsonlogger  # noqa: E402

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": _jsonlogger.JsonFormatter,
            "fmt": "%(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stderr",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": _LOG_LEVEL,
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": _LOG_LEVEL,
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": _LOG_LEVEL,
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            # DB query logging is noisy; silence below WARNING unless overridden.
            "level": max(logging.getLevelName(_LOG_LEVEL), logging.WARNING),
            "propagate": False,
        },
        "src": {
            "handlers": ["console"],
            "level": _LOG_LEVEL,
            "propagate": False,
        },
    },
}

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
