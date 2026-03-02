"""Tests for Django settings conventions."""

from django.conf import settings


class TestTimezoneSettings:
    """Ensure UTC and timezone-aware storage are configured."""

    def test_time_zone_is_utc(self):
        """TIME_ZONE must be UTC."""
        assert settings.TIME_ZONE == "UTC"

    def test_use_tz_is_enabled(self):
        """USE_TZ must be True so Django stores aware datetimes in UTC."""
        assert settings.USE_TZ is True
