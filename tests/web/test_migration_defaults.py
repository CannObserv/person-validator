"""Tests that data migrations pre-populate correct defaults."""

import pytest

from src.web.persons.models import AttributeLabel, ExternalPlatform


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
        actual = set(
            AttributeLabel.objects.filter(value_type=value_type).values_list("slug", flat=True)
        )
        assert expected_slugs.issubset(actual), f"{value_type}: missing {expected_slugs - actual}"

    def test_all_defaults_active(self):
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

    def test_all_expected_slugs_present(self):
        all_slugs = self.SOCIAL_SLUGS | self.AUTHORITY_SLUGS
        actual = set(ExternalPlatform.objects.values_list("slug", flat=True))
        assert all_slugs.issubset(actual)

    def test_all_defaults_active(self):
        all_slugs = self.SOCIAL_SLUGS | self.AUTHORITY_SLUGS
        inactive = ExternalPlatform.objects.filter(slug__in=all_slugs, is_active=False)
        assert inactive.count() == 0


@pytest.mark.django_db
class TestP2390MigrationSeed:
    """Verify that the 0015 data migration seeded P2390 correctly."""

    def test_p2390_exists(self):
        from src.web.persons.models import ExternalIdentifierProperty

        prop = ExternalIdentifierProperty.objects.get(wikidata_property_id="P2390")
        assert prop.slug == "ballotpedia-slug"
        assert prop.display == "Ballotpedia page slug"
        assert prop.formatter_url == ""
        assert prop.is_enabled is True

    def test_p2390_platform_is_null(self):
        """platform FK must be NULL so WikidataProvider emits the raw slug as text.

        When platform is set, WikidataProvider constructs the full URL and emits
        a platform_url attribute — but BallotpediaProvider reads the raw slug
        (e.g. 'Denny_Heck') not the constructed URL.
        """
        from src.web.persons.models import ExternalIdentifierProperty

        prop = ExternalIdentifierProperty.objects.get(wikidata_property_id="P2390")
        assert prop.platform is None

    def test_p2390_upsert_is_idempotent(self):
        """Running the seed function twice does not raise or duplicate rows."""
        import importlib

        from django.apps import apps as django_apps

        from src.web.persons.models import ExternalIdentifierProperty

        mod = importlib.import_module(
            "src.web.persons.migrations.0015_seed_p2390_ballotpedia_property"
        )

        # Run seed again (simulates running migration on existing data)
        mod.seed_ballotpedia_property(django_apps, None)
        count = ExternalIdentifierProperty.objects.filter(wikidata_property_id="P2390").count()
        assert count == 1
