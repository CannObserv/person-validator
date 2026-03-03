"""Tests for the EnrichmentRunner."""

import pytest

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
        result = runner.run(_make_person(id=person.pk))

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
        result = runner.run(_make_person(id=person.pk))

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
        result = runner.run(_make_person(id=person.pk))

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
        result = EnrichmentRunner(reg).run(_make_person(id=person.pk))

        assert result.attributes_saved == 0
        assert PersonAttribute.objects.filter(person=person).count() == 0

    def test_run_result_person_id(self):
        from src.web.persons.models import Person

        person = Person.objects.create(name="Alice Smith")
        reg = ProviderRegistry()
        result = EnrichmentRunner(reg).run(_make_person(id=person.pk))
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
        result = EnrichmentRunner(_make_registry(provider)).run(_make_person(id=person.pk))

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
        result = EnrichmentRunner(_make_registry(provider)).run(_make_person(id=person.pk))

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
        result = EnrichmentRunner(_make_registry(provider)).run(_make_person(id=person.pk))

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
        result = EnrichmentRunner(_make_registry(provider)).run(_make_person(id=person.pk))

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
        result = EnrichmentRunner(_make_registry(provider)).run(_make_person(id=person.pk))

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
        result = EnrichmentRunner(_make_registry(provider)).run(_make_person(id=person.pk))

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
        result = EnrichmentRunner(_make_registry(provider)).run(_make_person(id=person.pk))

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
        result = EnrichmentRunner(_make_registry(provider)).run(_make_person(id=person.pk))

        assert result.attributes_saved == 1
        attr = PersonAttribute.objects.get(person=person, key="address")
        assert attr.metadata["city"] == "Denver"
        assert attr.metadata["region"] == "CO"
        assert attr.metadata["label"] == ["home"]
        assert attr.metadata["components"]["spec"] == "usps-pub28"
