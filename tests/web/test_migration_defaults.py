"""Tests that data migration 0005 pre-populates correct defaults."""

import pytest


@pytest.mark.django_db
class TestAttributeLabelDefaults:
    """Verify default AttributeLabel rows from the data migration."""

    @pytest.mark.parametrize(
        "value_type,expected_slugs",
        [
            ("email", {"work", "home", "personal"}),
            ("phone", {"work", "home", "mobile", "personal"}),
            ("url", {"website", "blog", "work"}),
            ("platform_url", {"website", "blog", "work"}),
            ("location", {"home", "work", "current", "previous", "mailing"}),
        ],
    )
    def test_defaults_present(self, value_type, expected_slugs):
        from src.web.persons.models import AttributeLabel

        actual = set(
            AttributeLabel.objects.filter(value_type=value_type).values_list("slug", flat=True)
        )
        assert expected_slugs.issubset(actual), f"{value_type}: missing {expected_slugs - actual}"

    def test_all_defaults_active(self):
        from src.web.persons.models import AttributeLabel

        inactive = AttributeLabel.objects.filter(
            value_type__in=["email", "phone", "url", "platform_url", "location"],
            is_active=False,
        )
        assert inactive.count() == 0


@pytest.mark.django_db
class TestSocialPlatformDefaults:
    """Verify default SocialPlatform rows from the data migration."""

    EXPECTED = {"linkedin", "github", "twitter", "instagram", "facebook", "youtube", "tiktok"}

    def test_defaults_present(self):
        from src.web.persons.models import SocialPlatform

        actual = set(SocialPlatform.objects.values_list("slug", flat=True))
        assert self.EXPECTED.issubset(actual)

    def test_all_defaults_active(self):
        from src.web.persons.models import SocialPlatform

        inactive = SocialPlatform.objects.filter(slug__in=self.EXPECTED, is_active=False)
        assert inactive.count() == 0
