"""Tests for Django settings conventions."""

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


@pytest.mark.django_db
class TestForeignKeyEnforcement:
    """Verify SQLite foreign key constraints are enforced on Django connections."""

    def test_fk_pragma_is_on(self):
        """Every Django SQLite connection must have PRAGMA foreign_keys = ON."""
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys")
            row = cursor.fetchone()
        assert row[0] == 1
