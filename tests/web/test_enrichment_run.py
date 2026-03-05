"""Tests for EnrichmentRun model and runner integration."""

import pytest
from django.utils import timezone

from src.core.enrichment.base import EnrichmentResult, PersonData, Provider
from src.core.enrichment.registry import ProviderRegistry
from src.core.enrichment.runner import EnrichmentRunner


def _make_person(**kwargs) -> PersonData:
    defaults = {"id": "01TESTPERSON000000000000001", "name": "Alice Smith"}
    defaults.update(kwargs)
    return PersonData(**defaults)


def _make_provider(name: str, results: list[EnrichmentResult]) -> Provider:
    class _P(Provider):
        def enrich(self, person: PersonData) -> list[EnrichmentResult]:
            return results

    _P.name = name
    return _P()


def _make_registry(*providers: Provider) -> ProviderRegistry:
    reg = ProviderRegistry()
    for p in providers:
        reg.register(p)
    return reg


@pytest.mark.django_db
class TestEnrichmentRunModel:
    """Tests for the EnrichmentRun model structure and DB table."""

    def test_table_name(self):
        """EnrichmentRun maps to persons_enrichmentrun table."""
        from src.web.persons.models import EnrichmentRun

        assert EnrichmentRun._meta.db_table == "persons_enrichmentrun"

    def test_create_enrichment_run(self):
        """An EnrichmentRun record can be created."""
        from src.web.persons.models import EnrichmentRun, Person

        person = Person.objects.create(name="Alice Smith")
        run = EnrichmentRun.objects.create(
            person=person,
            provider="test_provider",
            status="completed",
            attributes_saved=3,
            attributes_skipped=1,
            warnings=[],
            triggered_by="manual",
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )
        assert run.pk is not None
        assert len(run.pk) == 26  # ULID

    def test_str_representation(self):
        """EnrichmentRun __str__ includes provider, person, and status."""
        from src.web.persons.models import EnrichmentRun, Person

        person = Person.objects.create(name="Alice Smith")
        run = EnrichmentRun.objects.create(
            person=person,
            provider="wikidata",
            status="completed",
            started_at=timezone.now(),
        )
        s = str(run)
        assert "wikidata" in s
        assert "completed" in s

    def test_status_choices(self):
        """STATUS_CHOICES includes all required values."""
        from src.web.persons.models import EnrichmentRun

        statuses = [c[0] for c in EnrichmentRun.STATUS_CHOICES]
        assert "running" in statuses
        assert "completed" in statuses
        assert "failed" in statuses
        assert "skipped" in statuses
        assert "no_match" in statuses

    def test_triggered_by_choices(self):
        """TRIGGERED_BY_CHOICES includes all required values."""
        from src.web.persons.models import EnrichmentRun

        choices = [c[0] for c in EnrichmentRun.TRIGGERED_BY_CHOICES]
        assert "cron" in choices
        assert "adjudication" in choices
        assert "manual" in choices
        assert "api" in choices

    def test_indexes_exist(self):
        """Both composite indexes are declared in the model Meta."""
        from src.web.persons.models import EnrichmentRun

        index_field_sets = [tuple(ix.fields) for ix in EnrichmentRun._meta.indexes]
        assert ("person", "provider", "-started_at") in index_field_sets
        assert ("provider", "status", "-started_at") in index_field_sets

    def test_default_ordering(self):
        """EnrichmentRun default ordering is -started_at."""
        from src.web.persons.models import EnrichmentRun

        assert EnrichmentRun._meta.ordering == ["-started_at"]

    def test_warnings_defaults_to_list(self):
        """warnings field defaults to an empty list."""
        from src.web.persons.models import EnrichmentRun, Person

        person = Person.objects.create(name="Alice Smith")
        run = EnrichmentRun.objects.create(
            person=person,
            provider="test",
            status="running",
            started_at=timezone.now(),
        )
        assert run.warnings == []

    def test_error_defaults_to_blank(self):
        """error field defaults to blank string."""
        from src.web.persons.models import EnrichmentRun, Person

        person = Person.objects.create(name="Alice Smith")
        run = EnrichmentRun.objects.create(
            person=person,
            provider="test",
            status="running",
            started_at=timezone.now(),
        )
        assert run.error == ""

    def test_completed_at_nullable(self):
        """completed_at may be null."""
        from src.web.persons.models import EnrichmentRun, Person

        person = Person.objects.create(name="Alice Smith")
        run = EnrichmentRun.objects.create(
            person=person,
            provider="test",
            status="running",
            started_at=timezone.now(),
        )
        assert run.completed_at is None

    def test_cascade_delete_with_person(self):
        """Deleting a person cascades to their EnrichmentRun records."""
        from src.web.persons.models import EnrichmentRun, Person

        person = Person.objects.create(name="Alice Smith")
        EnrichmentRun.objects.create(
            person=person,
            provider="test",
            status="completed",
            started_at=timezone.now(),
        )
        person_pk = person.pk
        person.delete()
        assert EnrichmentRun.objects.filter(person_id=person_pk).count() == 0


@pytest.mark.django_db
class TestRunnerCreatesEnrichmentRunRecords:
    """Runner integration: EnrichmentRun records are created/updated during runs."""

    def test_successful_run_creates_completed_record(self):
        """A successful provider run creates a 'completed' EnrichmentRun."""
        from src.web.persons.models import EnrichmentRun, Person

        person = Person.objects.create(name="Alice Smith")
        provider = _make_provider(
            "test_provider",
            [EnrichmentResult(key="employer", value="Acme", value_type="text", confidence=0.9)],
        )
        runner = EnrichmentRunner(_make_registry(provider))
        runner.run(_make_person(id=person.pk))

        run = EnrichmentRun.objects.get(person=person, provider="test_provider")
        assert run.status == "completed"
        assert run.attributes_saved == 1
        assert run.attributes_skipped == 0
        assert run.started_at is not None
        assert run.completed_at is not None

    def test_failed_provider_creates_failed_record(self):
        """A provider that raises creates a 'failed' EnrichmentRun."""
        from src.web.persons.models import EnrichmentRun, Person

        class BoomProvider(Provider):
            name = "boom"

            def enrich(self, person: PersonData) -> list[EnrichmentResult]:
                raise RuntimeError("kaboom")

        person = Person.objects.create(name="Alice Smith")
        runner = EnrichmentRunner(_make_registry(BoomProvider()))
        runner.run(_make_person(id=person.pk))

        run = EnrichmentRun.objects.get(person=person, provider="boom")
        assert run.status == "failed"
        assert "kaboom" in run.error
        assert run.completed_at is not None

    def test_skipped_attributes_counted_in_run_record(self):
        """Skipped attributes are reflected in the EnrichmentRun record."""
        from src.web.persons.models import EnrichmentRun, Person

        person = Person.objects.create(name="Alice Smith")
        provider = _make_provider(
            "test_provider",
            [
                EnrichmentResult(
                    key="email", value="bad-email", value_type="email", confidence=0.9
                ),
            ],
        )
        runner = EnrichmentRunner(_make_registry(provider))
        runner.run(_make_person(id=person.pk))

        run = EnrichmentRun.objects.get(person=person, provider="test_provider")
        assert run.status == "completed"
        assert run.attributes_saved == 0
        assert run.attributes_skipped == 1

    def test_warnings_persisted_in_run_record(self):
        """Label-strip warnings are stored in the EnrichmentRun.warnings field."""
        from src.web.persons.models import EnrichmentRun, Person

        person = Person.objects.create(name="Alice Smith")
        provider = _make_provider(
            "test_provider",
            [
                EnrichmentResult(
                    key="email",
                    value="alice@example.com",
                    value_type="email",
                    confidence=0.9,
                    metadata={"label": ["vip"]},
                )
            ],
        )
        runner = EnrichmentRunner(_make_registry(provider))
        runner.run(_make_person(id=person.pk))

        run = EnrichmentRun.objects.get(person=person, provider="test_provider")
        assert len(run.warnings) == 1
        assert "vip" in run.warnings[0]["message"]

    def test_triggered_by_default_is_manual(self):
        """triggered_by defaults to 'manual' when not specified."""
        from src.web.persons.models import EnrichmentRun, Person

        person = Person.objects.create(name="Alice Smith")
        provider = _make_provider(
            "test_provider",
            [EnrichmentResult(key="employer", value="Acme", value_type="text", confidence=0.9)],
        )
        runner = EnrichmentRunner(_make_registry(provider))
        runner.run(_make_person(id=person.pk))

        run = EnrichmentRun.objects.get(person=person, provider="test_provider")
        assert run.triggered_by == "manual"

    def test_triggered_by_cron_passed_through(self):
        """triggered_by='cron' is stored on the EnrichmentRun record."""
        from src.web.persons.models import EnrichmentRun, Person

        person = Person.objects.create(name="Alice Smith")
        provider = _make_provider(
            "test_provider",
            [EnrichmentResult(key="employer", value="Acme", value_type="text", confidence=0.9)],
        )
        runner = EnrichmentRunner(_make_registry(provider))
        runner.run(_make_person(id=person.pk), triggered_by="cron")

        run = EnrichmentRun.objects.get(person=person, provider="test_provider")
        assert run.triggered_by == "cron"

    def test_one_run_record_per_provider(self):
        """Each provider produces exactly one EnrichmentRun record per run call."""
        from src.web.persons.models import EnrichmentRun, Person

        person = Person.objects.create(name="Alice Smith")
        p1 = _make_provider(
            "provider_a",
            [EnrichmentResult(key="k1", value="v1", value_type="text", confidence=0.9)],
        )
        p2 = _make_provider(
            "provider_b",
            [EnrichmentResult(key="k2", value="v2", value_type="text", confidence=0.9)],
        )
        runner = EnrichmentRunner(_make_registry(p1, p2))
        runner.run(_make_person(id=person.pk))

        assert EnrichmentRun.objects.filter(person=person).count() == 2
        assert EnrichmentRun.objects.filter(person=person, provider="provider_a").count() == 1
        assert EnrichmentRun.objects.filter(person=person, provider="provider_b").count() == 1

    def test_disabled_provider_no_run_record(self):
        """Disabled providers produce no EnrichmentRun record."""
        from src.web.persons.models import EnrichmentRun, Person

        person = Person.objects.create(name="Alice Smith")
        provider = _make_provider(
            "test_provider",
            [EnrichmentResult(key="employer", value="Acme", value_type="text", confidence=0.9)],
        )
        reg = ProviderRegistry()
        reg.register(provider, enabled=False)
        runner = EnrichmentRunner(reg)
        runner.run(_make_person(id=person.pk))

        assert EnrichmentRun.objects.filter(person=person).count() == 0


@pytest.mark.django_db
class TestEnrichmentRunAdmin:
    """Tests for EnrichmentRun Django admin registration."""

    def test_admin_registered(self):
        """EnrichmentRun is registered with the Django admin site."""
        from django.contrib.admin import site as admin_site

        from src.web.persons.models import EnrichmentRun

        assert EnrichmentRun in admin_site._registry

    def test_list_display(self):
        """EnrichmentRunAdmin list_display contains required columns."""
        from django.contrib.admin.sites import AdminSite

        from src.web.persons.admin import EnrichmentRunAdmin
        from src.web.persons.models import EnrichmentRun

        admin = EnrichmentRunAdmin(EnrichmentRun, AdminSite())
        for field in (
            "person",
            "provider",
            "status",
            "attributes_saved",
            "attributes_skipped",
            "triggered_by",
            "started_at",
            "completed_at",
        ):
            assert field in admin.list_display, f"Missing from list_display: {field}"

    def test_list_filter(self):
        """EnrichmentRunAdmin filters by provider, status, triggered_by."""
        from django.contrib.admin.sites import AdminSite

        from src.web.persons.admin import EnrichmentRunAdmin
        from src.web.persons.models import EnrichmentRun

        admin = EnrichmentRunAdmin(EnrichmentRun, AdminSite())
        for field in ("provider", "status", "triggered_by"):
            assert field in admin.list_filter, f"Missing from list_filter: {field}"

    def test_search_fields(self):
        """EnrichmentRunAdmin search includes person name and provider."""
        from django.contrib.admin.sites import AdminSite

        from src.web.persons.admin import EnrichmentRunAdmin
        from src.web.persons.models import EnrichmentRun

        admin = EnrichmentRunAdmin(EnrichmentRun, AdminSite())
        assert "person__name" in admin.search_fields
        assert "provider" in admin.search_fields

    def test_all_fields_readonly(self):
        """All fields are read-only in EnrichmentRunAdmin (append-only log)."""
        from django.contrib.admin.sites import AdminSite

        from src.web.persons.admin import EnrichmentRunAdmin
        from src.web.persons.models import EnrichmentRun

        admin_instance = EnrichmentRunAdmin(EnrichmentRun, AdminSite())
        # get_readonly_fields with no obj returns the base set
        readonly = admin_instance.get_readonly_fields(None)
        expected_fields = {
            "id",
            "person",
            "provider",
            "status",
            "attributes_saved",
            "attributes_skipped",
            "warnings",
            "error",
            "triggered_by",
            "started_at",
            "completed_at",
        }
        for field in expected_fields:
            assert field in readonly, f"Field not readonly: {field}"
