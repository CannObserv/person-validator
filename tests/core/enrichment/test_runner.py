"""Tests for the EnrichmentRunner."""

import threading
import time

import pytest

from src.core.enrichment.base import (
    Dependency,
    EnrichmentResult,
    EnrichmentRunResult,
    PersonData,
    Provider,
)
from src.core.enrichment.registry import ProviderRegistry
from src.core.enrichment.runner import EnrichmentRunner
from tests.conftest import make_person as _make_person
from tests.conftest import make_provider as _make_provider
from tests.conftest import make_registry as _make_registry


def _aggregate(results: dict, person_id: str = "") -> EnrichmentRunResult:
    """Aggregate a dict[str, EnrichmentRunResult] into a single EnrichmentRunResult."""
    if not results:
        return EnrichmentRunResult(person_id=person_id)
    pid = next(iter(results.values())).person_id or person_id
    agg = EnrichmentRunResult(person_id=pid)
    for r in results.values():
        agg.attributes_saved += r.attributes_saved
        agg.attributes_skipped += r.attributes_skipped
        agg.warnings.extend(r.warnings)
    return agg


@pytest.mark.django_db(transaction=True)
class TestRunnerBasic:
    """Basic runner behaviour: persist, skip, continue on failure."""

    def test_run_persists_text_attribute(self):
        from src.web.persons.models import Person, PersonAttribute

        person = Person.objects.create(name="Alice Smith")
        provider = _make_provider(
            "acme",
            [
                EnrichmentResult(
                    key="employer", value="Acme Corp", value_type="text", confidence=0.9
                )
            ],
        )
        runner = EnrichmentRunner(_make_registry(provider))
        result = _aggregate(runner.run(_make_person(id=person.pk)))

        assert result.attributes_saved == 1
        assert result.attributes_skipped == 0
        attr = PersonAttribute.objects.get(person=person, key="employer")
        assert attr.value == "Acme Corp"
        assert attr.source == "acme"
        assert attr.value_type == "text"

    def test_invalid_attribute_skipped(self):
        from src.web.persons.models import Person, PersonAttribute

        person = Person.objects.create(name="Alice Smith")
        provider = _make_provider(
            "acme",
            [
                EnrichmentResult(
                    key="email", value="not-an-email", value_type="email", confidence=0.9
                )
            ],
        )
        runner = EnrichmentRunner(_make_registry(provider))
        result = _aggregate(runner.run(_make_person(id=person.pk)))

        assert result.attributes_saved == 0
        assert result.attributes_skipped == 1
        assert PersonAttribute.objects.filter(person=person).count() == 0

    def test_failing_provider_does_not_abort_run(self):
        from src.web.persons.models import Person, PersonAttribute

        class BoomProvider(Provider):
            name = "boom"

            def enrich(self, person: PersonData) -> list[EnrichmentResult]:
                raise RuntimeError("kaboom")

        good = _make_provider(
            "good",
            [EnrichmentResult(key="employer", value="Acme", value_type="text", confidence=1.0)],
        )
        reg = ProviderRegistry()
        reg.register(BoomProvider())
        reg.register(good)
        runner = EnrichmentRunner(reg)
        person = Person.objects.create(name="Alice Smith")
        result = _aggregate(runner.run(_make_person(id=person.pk)))

        assert result.attributes_saved == 1
        assert PersonAttribute.objects.filter(person=person).count() == 1

    def test_disabled_provider_not_run(self):
        from src.web.persons.models import Person, PersonAttribute

        provider = _make_provider(
            "acme",
            [EnrichmentResult(key="employer", value="Acme", value_type="text", confidence=1.0)],
        )
        reg = ProviderRegistry()
        reg.register(provider, enabled=False)
        person = Person.objects.create(name="Alice Smith")
        result = _aggregate(EnrichmentRunner(reg).run(_make_person(id=person.pk)))

        assert result.attributes_saved == 0
        assert PersonAttribute.objects.filter(person=person).count() == 0

    def test_run_result_person_id(self):
        from src.web.persons.models import Person

        person = Person.objects.create(name="Alice Smith")
        reg = ProviderRegistry()
        pd = _make_person(id=person.pk)
        result = _aggregate(EnrichmentRunner(reg).run(pd), person_id=str(person.pk))
        assert result.person_id == person.pk


@pytest.mark.django_db
class TestRunnerLabelStripping:
    """Label validation: unknown slugs stripped, warnings emitted."""

    def test_known_label_preserved(self):
        from src.web.persons.models import Person, PersonAttribute

        person = Person.objects.create(name="Alice Smith")
        provider = _make_provider(
            "acme",
            [
                EnrichmentResult(
                    key="email",
                    value="alice@example.com",
                    value_type="email",
                    confidence=0.9,
                    metadata={"label": ["work"]},
                )
            ],
        )
        runner = EnrichmentRunner(_make_registry(provider))
        result = _aggregate(runner.run(_make_person(id=person.pk)))

        assert result.attributes_saved == 1
        assert result.warnings == []
        attr = PersonAttribute.objects.get(person=person, key="email")
        assert attr.metadata["label"] == ["work"]

    def test_unknown_label_stripped_with_warning(self):
        from src.web.persons.models import Person, PersonAttribute

        person = Person.objects.create(name="Alice Smith")
        provider = _make_provider(
            "acme",
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
        result = _aggregate(runner.run(_make_person(id=person.pk)))

        assert result.attributes_saved == 1
        assert len(result.warnings) == 1
        assert "vip" in result.warnings[0].message
        attr = PersonAttribute.objects.get(person=person, key="email")
        # label was stripped — metadata label list should be absent or empty
        assert not (attr.metadata or {}).get("label")

    def test_mixed_labels_partial_strip(self):
        from src.web.persons.models import Person, PersonAttribute

        person = Person.objects.create(name="Alice Smith")
        provider = _make_provider(
            "acme",
            [
                EnrichmentResult(
                    key="email",
                    value="alice@example.com",
                    value_type="email",
                    confidence=0.9,
                    metadata={"label": ["work", "vip"]},
                )
            ],
        )
        runner = EnrichmentRunner(_make_registry(provider))
        result = _aggregate(runner.run(_make_person(id=person.pk)))

        assert result.attributes_saved == 1
        assert len(result.warnings) == 1
        attr = PersonAttribute.objects.get(person=person, key="email")
        assert attr.metadata["label"] == ["work"]

    def test_all_labels_stripped_attribute_still_persisted(self):
        from src.web.persons.models import Person, PersonAttribute

        person = Person.objects.create(name="Alice Smith")
        provider = _make_provider(
            "acme",
            [
                EnrichmentResult(
                    key="email",
                    value="alice@example.com",
                    value_type="email",
                    confidence=0.9,
                    metadata={"label": ["vip", "priority"]},
                )
            ],
        )
        runner = EnrichmentRunner(_make_registry(provider))
        result = _aggregate(runner.run(_make_person(id=person.pk)))

        assert result.attributes_saved == 1
        assert len(result.warnings) == 2
        assert PersonAttribute.objects.filter(person=person).count() == 1


@pytest.mark.django_db
class TestRunnerPlatformStripping:
    """Platform validation for platform_url attributes."""

    def test_known_platform_preserved(self):
        from src.web.persons.models import Person, PersonAttribute

        person = Person.objects.create(name="Alice Smith")
        provider = _make_provider(
            "acme",
            [
                EnrichmentResult(
                    key="social",
                    value="https://linkedin.com/in/alice",
                    value_type="platform_url",
                    confidence=0.9,
                    metadata={"platform": "linkedin"},
                )
            ],
        )
        runner = EnrichmentRunner(_make_registry(provider))
        result = _aggregate(runner.run(_make_person(id=person.pk)))

        assert result.attributes_saved == 1
        assert result.warnings == []
        attr = PersonAttribute.objects.get(person=person, key="social")
        assert attr.metadata["platform"] == "linkedin"

    def test_unknown_platform_stripped_with_warning(self):
        from src.web.persons.models import Person, PersonAttribute

        person = Person.objects.create(name="Alice Smith")
        provider = _make_provider(
            "acme",
            [
                EnrichmentResult(
                    key="social",
                    value="https://mastodon.social/@alice",
                    value_type="platform_url",
                    confidence=0.9,
                    metadata={"platform": "mastodon"},
                )
            ],
        )
        runner = EnrichmentRunner(_make_registry(provider))
        result = _aggregate(runner.run(_make_person(id=person.pk)))

        assert result.attributes_saved == 1
        assert len(result.warnings) == 1
        assert "mastodon" in result.warnings[0].message
        attr = PersonAttribute.objects.get(person=person, key="social")
        assert "platform" not in (attr.metadata or {})

    def test_platform_url_persisted_without_platform(self):
        """platform_url attribute is kept even when platform is stripped."""
        from src.web.persons.models import Person, PersonAttribute

        person = Person.objects.create(name="Alice Smith")
        provider = _make_provider(
            "acme",
            [
                EnrichmentResult(
                    key="social",
                    value="https://unknown.social/@alice",
                    value_type="platform_url",
                    confidence=0.85,
                    metadata={"platform": "unknownnet"},
                )
            ],
        )
        runner = EnrichmentRunner(_make_registry(provider))
        result = _aggregate(runner.run(_make_person(id=person.pk)))

        assert result.attributes_saved == 1
        assert PersonAttribute.objects.filter(person=person, key="social").count() == 1


@pytest.mark.django_db
class TestRunnerLocationRoundtrip:
    """Location metadata round-trips through persist."""

    def test_location_metadata_persisted(self):
        from src.web.persons.models import Person, PersonAttribute

        person = Person.objects.create(name="Alice Smith")
        provider = _make_provider(
            "acme",
            [
                EnrichmentResult(
                    key="address",
                    value="123 MAIN ST, DENVER CO 80202",
                    value_type="location",
                    confidence=0.9,
                    metadata={
                        "address_line_1": "123 Main St",
                        "address_line_2": "",
                        "city": "Denver",
                        "region": "CO",
                        "postal_code": "80202",
                        "country": "US",
                        "standardized": "123 MAIN ST, DENVER CO 80202",
                        "components": {
                            "spec": "usps-pub28",
                            "spec_version": "2024-07",
                            "values": {},
                        },
                        "label": ["home"],
                    },
                )
            ],
        )
        runner = EnrichmentRunner(_make_registry(provider))
        result = _aggregate(runner.run(_make_person(id=person.pk)))

        assert result.attributes_saved == 1
        attr = PersonAttribute.objects.get(person=person, key="address")
        assert attr.metadata["city"] == "Denver"
        assert attr.metadata["region"] == "CO"
        assert attr.metadata["label"] == ["home"]
        assert attr.metadata["components"]["spec"] == "usps-pub28"


@pytest.mark.django_db
class TestRunnerTriggeredBy:
    """triggered_by is plumbed through to EnrichmentRun."""

    def test_triggered_by_default_manual(self):
        from src.web.persons.models import EnrichmentRun, Person

        person = Person.objects.create(name="Alice Smith")
        provider = _make_provider(
            "acme",
            [EnrichmentResult(key="employer", value="Acme", value_type="text", confidence=1.0)],
        )
        EnrichmentRunner(_make_registry(provider)).run(_make_person(id=person.pk))
        run = EnrichmentRun.objects.get(person=person, provider="acme")
        assert run.triggered_by == "manual"

    def test_triggered_by_custom_value(self):
        from src.web.persons.models import EnrichmentRun, Person

        person = Person.objects.create(name="Alice Smith")
        provider = _make_provider(
            "acme",
            [EnrichmentResult(key="employer", value="Acme", value_type="text", confidence=1.0)],
        )
        EnrichmentRunner(_make_registry(provider)).run(
            _make_person(id=person.pk), triggered_by="admin"
        )
        run = EnrichmentRun.objects.get(person=person, provider="acme")
        assert run.triggered_by == "admin"


@pytest.mark.django_db(transaction=True)
class TestRunnerProviderNames:
    """provider_names parameter filters which providers run."""

    def test_unknown_provider_name_logs_warning(self):
        from unittest.mock import patch

        from src.web.persons.models import Person

        person = Person.objects.create(name="Alice Smith")
        a = _make_provider(
            "a", [EnrichmentResult(key="ka", value="va", value_type="text", confidence=1.0)]
        )
        with patch("src.core.enrichment.runner.logger") as mock_logger:
            EnrichmentRunner(_make_registry(a)).run(
                _make_person(id=person.pk), provider_names=["a", "nonexistent"]
            )
        warning_messages = [str(call) for call in mock_logger.warning.call_args_list]
        assert any("nonexistent" in msg for msg in warning_messages)

    def test_all_run_when_names_is_none(self):
        from src.web.persons.models import EnrichmentRun, Person

        person = Person.objects.create(name="Alice Smith")
        a = _make_provider(
            "a", [EnrichmentResult(key="ka", value="va", value_type="text", confidence=1.0)]
        )
        b = _make_provider(
            "b", [EnrichmentResult(key="kb", value="vb", value_type="text", confidence=1.0)]
        )
        EnrichmentRunner(_make_registry(a, b)).run(_make_person(id=person.pk), provider_names=None)
        assert EnrichmentRun.objects.filter(person=person).count() == 2

    def test_only_named_provider_runs(self):
        from src.web.persons.models import EnrichmentRun, Person

        person = Person.objects.create(name="Alice Smith")
        a = _make_provider(
            "a", [EnrichmentResult(key="ka", value="va", value_type="text", confidence=1.0)]
        )
        b = _make_provider(
            "b", [EnrichmentResult(key="kb", value="vb", value_type="text", confidence=1.0)]
        )
        EnrichmentRunner(_make_registry(a, b)).run(_make_person(id=person.pk), provider_names=["a"])
        assert EnrichmentRun.objects.filter(person=person, provider="a").count() == 1
        assert EnrichmentRun.objects.filter(person=person, provider="b").count() == 0


@pytest.mark.django_db
class TestRunnerSkippedProviders:
    """Providers that fail can_run() get an EnrichmentRun with status='skipped'."""

    def test_skipped_provider_logged(self):
        from src.web.persons.models import EnrichmentRun, Person

        class WikipediaProvider(Provider):
            name = "wikipedia"
            dependencies = [Dependency(attribute_key="wikidata_qid")]
            output_keys = []

            def enrich(self, person: PersonData) -> list[EnrichmentResult]:
                return []  # should never be called

        person = Person.objects.create(name="Alice Smith")
        reg = ProviderRegistry()
        reg.register(WikipediaProvider())
        result = EnrichmentRunner(reg).run(_make_person(id=person.pk))

        run = EnrichmentRun.objects.get(person=person, provider="wikipedia")
        assert run.status == "skipped"
        assert result["wikipedia"].attributes_saved == 0

    def test_skipped_provider_enrich_not_called(self):
        from src.web.persons.models import Person

        called = []

        class DepProvider(Provider):
            name = "dep"
            dependencies = [Dependency(attribute_key="missing_key")]
            output_keys = []

            def enrich(self, person: PersonData) -> list[EnrichmentResult]:
                called.append(True)
                return []

        person = Person.objects.create(name="Alice Smith")
        reg = ProviderRegistry()
        reg.register(DepProvider())
        EnrichmentRunner(reg).run(_make_person(id=person.pk))
        assert called == []


@pytest.mark.django_db
class TestRunnerExistingAttributesRefresh:
    """existing_attributes on PersonData is refreshed between rounds."""

    def test_downstream_provider_sees_upstream_output(self):
        """WikidataProvider writes wikidata_qid; WikipediaProvider reads it via can_run."""
        from src.web.persons.models import EnrichmentRun, Person

        class WikidataProvider(Provider):
            name = "wikidata"
            dependencies = []
            output_keys = ["wikidata_qid"]

            def enrich(self, person: PersonData) -> list[EnrichmentResult]:
                return [
                    EnrichmentResult(
                        key="wikidata_qid", value="Q42", value_type="text", confidence=1.0
                    )
                ]

        class WikipediaProvider(Provider):
            name = "wikipedia"
            dependencies = [Dependency(attribute_key="wikidata_qid")]
            output_keys = []

            def enrich(self, person: PersonData) -> list[EnrichmentResult]:
                return [
                    EnrichmentResult(
                        key="wikipedia_url",
                        value="https://en.wikipedia.org/wiki/Douglas_Adams",
                        value_type="url",
                        confidence=1.0,
                    )
                ]

        person = Person.objects.create(name="Douglas Adams")
        reg = ProviderRegistry()
        reg.register(WikidataProvider())
        reg.register(WikipediaProvider())
        result = EnrichmentRunner(reg).run(_make_person(id=person.pk))

        total_saved = sum(r.attributes_saved for r in result.values())
        assert total_saved == 2
        # Both providers should have completed runs
        assert EnrichmentRun.objects.filter(person=person, status="completed").count() == 2


@pytest.mark.django_db(transaction=True)
class TestRunnerParallelExecution:
    """Independent providers run concurrently within a round."""

    def test_parallel_providers_overlap_in_time(self):
        """Two slow providers in the same round should overlap (not serialize)."""
        from src.web.persons.models import Person

        start_times: list[float] = []
        lock = threading.Lock()

        def _make_slow(name: str, delay: float) -> Provider:
            class _P(Provider):
                dependencies = []
                output_keys = []

                def enrich(self, person: PersonData) -> list[EnrichmentResult]:
                    with lock:
                        start_times.append(time.monotonic())
                    time.sleep(delay)
                    return []

            _P.name = name
            return _P()

        slow_a = _make_slow("slow_a", 0.1)
        slow_b = _make_slow("slow_b", 0.1)

        person = Person.objects.create(name="Alice Smith")
        reg = ProviderRegistry()
        reg.register(slow_a)
        reg.register(slow_b)

        wall_start = time.monotonic()
        EnrichmentRunner(reg).run(_make_person(id=person.pk))
        wall_elapsed = time.monotonic() - wall_start

        # If serial: ~0.2s; if parallel: ~0.1s. Allow generous margin.
        assert wall_elapsed < 0.18, f"Providers did not run in parallel: {wall_elapsed:.3f}s"
        assert len(start_times) == 2


@pytest.mark.django_db(transaction=True)
class TestRunnerReturnsDictByProviderName:
    """run() returns dict[str, EnrichmentRunResult]."""

    def test_returns_dict_keyed_by_provider_name(self):
        from src.web.persons.models import Person

        person = Person.objects.create(name="Alice Smith")
        a = _make_provider(
            "a", [EnrichmentResult(key="ka", value="va", value_type="text", confidence=1.0)]
        )
        b = _make_provider(
            "b", [EnrichmentResult(key="kb", value="vb", value_type="text", confidence=1.0)]
        )
        result = EnrichmentRunner(_make_registry(a, b)).run(_make_person(id=person.pk))
        assert isinstance(result, dict)
        assert "a" in result
        assert "b" in result
        assert result["a"].attributes_saved == 1
        assert result["b"].attributes_saved == 1

    def test_skipped_provider_in_result(self):
        from src.web.persons.models import Person

        class DepProvider(Provider):
            name = "dep"
            dependencies = [Dependency(attribute_key="missing_key")]
            output_keys = []

            def enrich(self, person: PersonData) -> list[EnrichmentResult]:
                return []

        person = Person.objects.create(name="Alice Smith")
        reg = ProviderRegistry()
        reg.register(DepProvider())
        result = EnrichmentRunner(reg).run(_make_person(id=person.pk))
        assert "dep" in result
