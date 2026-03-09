"""Tests for the run_enrichment_cron management command."""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_person(name="Alice Smith"):
    from src.web.persons.models import Person

    return Person.objects.create(name=name)


def _make_enrichment_run(person, provider, *, status="completed", age_hours=200):
    """Create an EnrichmentRun for the given person+provider, started age_hours ago."""
    from src.web.persons.models import EnrichmentRun

    started = timezone.now() - timedelta(hours=age_hours)
    return EnrichmentRun.objects.create(
        person=person,
        provider=provider,
        status=status,
        triggered_by="test",
        started_at=started,
        completed_at=started + timedelta(seconds=1),
    )


def _run_cron(**options):
    out = StringIO()
    call_command("run_enrichment_cron", stdout=out, **options)
    return out.getvalue()


# ---------------------------------------------------------------------------
# Staleness logic
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCronStalenessLogic:
    """run_enrichment_cron correctly identifies stale providers per person."""

    @patch("src.web.persons.management.commands.run_enrichment_cron.run_enrichment_for_person")
    def test_never_run_person_is_stale(self, mock_enrich):
        """Person with no EnrichmentRun is enriched for all providers."""
        person = _make_person()
        _run_cron()
        mock_enrich.assert_called_once()
        call_kwargs = mock_enrich.call_args.kwargs
        assert call_kwargs["person_id"] == str(person.pk)
        assert call_kwargs["triggered_by"] == "cron"

    @patch("src.web.persons.management.commands.run_enrichment_cron.run_enrichment_for_person")
    def test_fresh_run_person_is_not_stale(self, mock_enrich):
        """Person enriched within refresh_interval is skipped."""
        person = _make_person()
        # Wikidata refresh_interval = 7 days; 1 hour ago is within interval
        _make_enrichment_run(person, "wikidata", age_hours=1)
        _make_enrichment_run(person, "wikipedia", age_hours=1)
        _make_enrichment_run(person, "ballotpedia", age_hours=1)
        _run_cron()
        mock_enrich.assert_not_called()

    @patch("src.web.persons.management.commands.run_enrichment_cron.run_enrichment_for_person")
    def test_stale_run_person_is_re_enriched(self, mock_enrich):
        """Person enriched longer ago than refresh_interval is re-enriched."""
        person = _make_person()
        # 200 hours (>7 days) is stale for all providers
        _make_enrichment_run(person, "wikidata", age_hours=200)
        _make_enrichment_run(person, "wikipedia", age_hours=200)
        _make_enrichment_run(person, "ballotpedia", age_hours=200)
        _run_cron()
        mock_enrich.assert_called_once()

    @patch("src.web.persons.management.commands.run_enrichment_cron.run_enrichment_for_person")
    def test_failed_run_is_retried(self, mock_enrich):
        """A person whose last run for a provider failed is re-enriched."""
        person = _make_person()
        # Even if failed recently, it should be retried
        _make_enrichment_run(person, "wikidata", status="failed", age_hours=1)
        _make_enrichment_run(person, "wikipedia", age_hours=1)
        _make_enrichment_run(person, "ballotpedia", age_hours=1)
        _run_cron()
        mock_enrich.assert_called_once()
        call_kwargs = mock_enrich.call_args.kwargs
        assert "wikidata" in call_kwargs["provider_names"]

    @patch("src.web.persons.management.commands.run_enrichment_cron.run_enrichment_for_person")
    def test_only_stale_providers_passed(self, mock_enrich):
        """provider_names contains only the stale providers, not fresh ones."""
        person = _make_person()
        _make_enrichment_run(person, "wikidata", age_hours=200)   # stale
        _make_enrichment_run(person, "wikipedia", age_hours=1)    # fresh
        _make_enrichment_run(person, "ballotpedia", age_hours=200)  # stale
        _run_cron()
        mock_enrich.assert_called_once()
        call_kwargs = mock_enrich.call_args.kwargs
        assert "wikidata" in call_kwargs["provider_names"]
        assert "ballotpedia" in call_kwargs["provider_names"]
        assert "wikipedia" not in call_kwargs["provider_names"]


# ---------------------------------------------------------------------------
# Rejected-review skip
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCronRejectedReviewSkip:
    """Wikidata provider is skipped for persons with a rejected WikidataCandidateReview."""

    @patch("src.web.persons.management.commands.run_enrichment_cron.run_enrichment_for_person")
    def test_rejected_wikidata_review_skips_wikidata_provider(self, mock_enrich):
        """Wikidata is excluded from provider_names when person has a rejected review."""
        from src.web.persons.models import WikidataCandidateReview

        person = _make_person()
        WikidataCandidateReview.objects.create(
            person=person,
            query_name="Alice Smith",
            candidates=[],
            status="rejected",
        )
        _run_cron()
        if mock_enrich.called:
            call_kwargs = mock_enrich.call_args.kwargs
            assert "wikidata" not in call_kwargs.get("provider_names", []), (
                "Wikidata must not run for a person with a rejected review"
            )

    @patch("src.web.persons.management.commands.run_enrichment_cron.run_enrichment_for_person")
    def test_non_rejected_review_does_not_skip_wikidata(self, mock_enrich):
        """A pending or accepted review does not suppress Wikidata re-enrichment."""
        from src.web.persons.models import WikidataCandidateReview

        person = _make_person()
        WikidataCandidateReview.objects.create(
            person=person,
            query_name="Alice Smith",
            candidates=[],
            status="pending",
        )
        _run_cron()
        mock_enrich.assert_called_once()
        call_kwargs = mock_enrich.call_args.kwargs
        assert "wikidata" in call_kwargs["provider_names"]


# ---------------------------------------------------------------------------
# --dry-run flag
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCronDryRun:
    """--dry-run prints what would run without executing enrichment."""

    @patch("src.web.persons.management.commands.run_enrichment_cron.run_enrichment_for_person")
    def test_dry_run_does_not_call_enrichment(self, mock_enrich):
        """run_enrichment_for_person is never called in dry-run mode."""
        _make_person()
        _run_cron(dry_run=True)
        mock_enrich.assert_not_called()

    @patch("src.web.persons.management.commands.run_enrichment_cron.run_enrichment_for_person")
    def test_dry_run_output_mentions_person(self, mock_enrich):
        """Dry-run output identifies the person that would be enriched."""
        person = _make_person("Denny Heck")
        output = _run_cron(dry_run=True)
        assert "Denny Heck" in output or str(person.pk) in output


# ---------------------------------------------------------------------------
# --provider flag
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCronProviderFlag:
    """--provider limits enrichment to a single named provider."""

    @patch("src.web.persons.management.commands.run_enrichment_cron.run_enrichment_for_person")
    def test_provider_flag_limits_to_named_provider(self, mock_enrich):
        """With --provider wikidata, only wikidata is in provider_names."""
        _make_person()
        _run_cron(provider="wikidata")
        if mock_enrich.called:
            call_kwargs = mock_enrich.call_args.kwargs
            assert call_kwargs["provider_names"] == ["wikidata"]

    @patch("src.web.persons.management.commands.run_enrichment_cron.run_enrichment_for_person")
    def test_unknown_provider_flag_runs_nothing(self, mock_enrich):
        """An unknown provider name results in no enrichment calls."""
        _make_person()
        _run_cron(provider="nonexistent_provider")
        mock_enrich.assert_not_called()


# ---------------------------------------------------------------------------
# --person-id flag
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCronPersonIdFlag:
    """--person-id enriches a single person regardless of staleness."""

    @patch("src.web.persons.management.commands.run_enrichment_cron.run_enrichment_for_person")
    def test_person_id_bypasses_staleness(self, mock_enrich):
        """--person-id runs even when all providers are fresh."""
        person = _make_person()
        _make_enrichment_run(person, "wikidata", age_hours=1)
        _make_enrichment_run(person, "wikipedia", age_hours=1)
        _make_enrichment_run(person, "ballotpedia", age_hours=1)
        _run_cron(person_id=str(person.pk))
        mock_enrich.assert_called_once()
        call_kwargs = mock_enrich.call_args.kwargs
        assert call_kwargs["person_id"] == str(person.pk)

    @patch("src.web.persons.management.commands.run_enrichment_cron.run_enrichment_for_person")
    def test_person_id_runs_all_providers(self, mock_enrich):
        """--person-id passes provider_names=None (all providers) to the runner."""
        person = _make_person()
        _run_cron(person_id=str(person.pk))
        mock_enrich.assert_called_once()
        call_kwargs = mock_enrich.call_args.kwargs
        assert call_kwargs.get("provider_names") is None


# ---------------------------------------------------------------------------
# --limit flag
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCronLimitFlag:
    """--limit caps the total persons processed."""

    @patch("src.web.persons.management.commands.run_enrichment_cron.run_enrichment_for_person")
    def test_limit_caps_enrichment_calls(self, mock_enrich):
        """With --limit 1 and 3 persons, only one enrichment call is made."""
        for i in range(3):
            _make_person(f"Person {i}")
        _run_cron(limit=1)
        assert mock_enrich.call_count <= 1


# ---------------------------------------------------------------------------
# Empty-table auto-sync integration
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCronAutoSync:
    """run_enrichment_cron triggers sync_wikidata_properties when table is empty."""

    @patch("src.web.persons.management.commands.run_enrichment_cron.call_command")
    def test_calls_sync_when_table_empty(self, mock_call_command):
        """sync_wikidata_properties is called when ExternalIdentifierProperty is empty."""
        from src.web.persons.models import ExternalIdentifierProperty

        ExternalIdentifierProperty.objects.all().delete()
        _make_person()

        with patch(
            "src.web.persons.management.commands.run_enrichment_cron.run_enrichment_for_person"
        ):
            _run_cron()

        sync_calls = [
            c for c in mock_call_command.call_args_list
            if "sync_wikidata_properties" in str(c)
        ]
        assert len(sync_calls) >= 1, (
            "Expected sync_wikidata_properties to be called when table is empty"
        )

    @patch("src.web.persons.management.commands.run_enrichment_cron.call_command")
    def test_does_not_call_sync_when_table_populated(self, mock_call_command):
        """sync_wikidata_properties is NOT called when table has entries."""
        from src.web.persons.models import ExternalIdentifierProperty

        assert ExternalIdentifierProperty.objects.exists()
        _make_person()

        with patch(
            "src.web.persons.management.commands.run_enrichment_cron.run_enrichment_for_person"
        ):
            _run_cron()

        sync_calls = [
            c for c in mock_call_command.call_args_list
            if "sync_wikidata_properties" in str(c)
        ]
        assert len(sync_calls) == 0, (
            "sync_wikidata_properties must not be called when table is populated"
        )
