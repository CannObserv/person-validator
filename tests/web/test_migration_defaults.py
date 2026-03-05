"""Tests that data migrations pre-populate correct defaults."""

import pytest


@pytest.mark.django_db
class TestAttributeLabelDefaults:
    """Verify default AttributeLabel rows from the data migration."""

    @pytest.mark.parametrize(
        "value_type,expected_slugs",
        [
            ("email", {"work", "personal"}),
            ("phone", {"work", "home", "mobile", "personal"}),
            ("url", {"website", "blog", "work"}),
            ("platform_url", {"work", "personal"}),
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
class TestExternalPlatformDefaults:
    """Verify default ExternalPlatform rows from the data migrations."""

    SOCIAL_SLUGS = {"linkedin", "github", "twitter", "instagram", "facebook", "youtube", "tiktok"}
    AUTHORITY_SLUGS = {
        "wikidata",
        "wikipedia",
        "viaf",
        "isni",
        "loc",
        "gnd",
        "orcid",
        "imdb",
        "musicbrainz",
        "ballotpedia",
        "opensecrets",
    }

    def test_social_defaults_present(self):
        from src.web.persons.models import ExternalPlatform

        actual = set(ExternalPlatform.objects.values_list("slug", flat=True))
        assert self.SOCIAL_SLUGS.issubset(actual)

    def test_authority_defaults_present(self):
        from src.web.persons.models import ExternalPlatform

        actual = set(ExternalPlatform.objects.values_list("slug", flat=True))
        assert self.AUTHORITY_SLUGS.issubset(actual)

    def test_all_defaults_active(self):
        from src.web.persons.models import ExternalPlatform

        all_slugs = self.SOCIAL_SLUGS | self.AUTHORITY_SLUGS
        inactive = ExternalPlatform.objects.filter(slug__in=all_slugs, is_active=False)
        assert inactive.count() == 0
