"""Tests for Django settings conventions."""

import logging

import pytest
from django.conf import settings
from django.db import connection


class TestTimezoneSettings:
    """Ensure UTC and timezone-aware storage are configured."""

    def test_time_zone_is_utc(self):
        """TIME_ZONE must be UTC."""
        assert settings.TIME_ZONE == "UTC"

    def test_use_tz_is_enabled(self):
        """USE_TZ must be True so Django stores aware datetimes in UTC."""
        assert settings.USE_TZ is True


class TestLoggingSettings:
    """Verify the LOGGING dict is present and correctly structured."""

    def test_logging_key_present(self):
        """settings.LOGGING must exist."""
        assert hasattr(settings, "LOGGING")

    def test_logging_version(self):
        """LOGGING['version'] must be 1."""
        assert settings.LOGGING["version"] == 1

    def test_console_handler_defined(self):
        """A 'console' handler must be defined."""
        assert "console" in settings.LOGGING["handlers"]

    def test_console_handler_uses_json_formatter(self):
        """The console handler must reference the 'json' formatter."""
        handler = settings.LOGGING["handlers"]["console"]
        assert handler["formatter"] == "json"

    def test_json_formatter_defined(self):
        """A 'json' formatter must be defined using pythonjsonlogger."""
        formatters = settings.LOGGING["formatters"]
        assert "json" in formatters
        assert "pythonjsonlogger" in formatters["json"]["()"].__module__

    def test_django_logger_configured(self):
        """The 'django' logger must be wired to the console handler."""
        loggers = settings.LOGGING["loggers"]
        assert "django" in loggers
        assert "console" in loggers["django"]["handlers"]

    def test_django_request_logger_configured(self):
        """The 'django.request' logger must be wired to the console handler."""
        loggers = settings.LOGGING["loggers"]
        assert "django.request" in loggers
        assert "console" in loggers["django.request"]["handlers"]

    def test_django_security_logger_configured(self):
        """The 'django.security' logger must be wired to the console handler."""
        loggers = settings.LOGGING["loggers"]
        assert "django.security" in loggers
        assert "console" in loggers["django.security"]["handlers"]

    def test_django_db_backends_logger_configured(self):
        """The 'django.db.backends' logger must be wired to the console handler."""
        loggers = settings.LOGGING["loggers"]
        assert "django.db.backends" in loggers
        assert "console" in loggers["django.db.backends"]["handlers"]

    def test_django_logger_level_is_string(self):
        """The 'django' logger level in LOGGING must be a valid level string."""
        level = settings.LOGGING["loggers"]["django"]["level"]
        assert logging.getLevelName(level) != f"Level {level}"


@pytest.mark.django_db
class TestForeignKeyEnforcement:
    """Verify SQLite foreign key constraints are enforced on Django connections."""

    def test_fk_pragma_is_on(self):
        """Every Django SQLite connection must have PRAGMA foreign_keys = ON."""
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys")
            row = cursor.fetchone()
        assert row[0] == 1
