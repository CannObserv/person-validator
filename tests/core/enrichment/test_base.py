"""Tests for base enrichment dataclasses, Provider ABC, and package exports."""

import pytest

from src.core.enrichment.base import (
    EnrichmentResult,
    EnrichmentRunResult,
    EnrichmentWarning,
    PersonData,
    Provider,
)


class TestEnrichmentResult:
    """Tests for the EnrichmentResult dataclass."""

    def test_required_fields(self):
        r = EnrichmentResult(key="employer", value="Acme")
        assert r.key == "employer"
        assert r.value == "Acme"

    def test_value_type_defaults_to_text(self):
        r = EnrichmentResult(key="x", value="y")
        assert r.value_type == "text"

    def test_confidence_defaults_to_one(self):
        r = EnrichmentResult(key="x", value="y")
        assert r.confidence == 1.0

    def test_metadata_defaults_none(self):
        r = EnrichmentResult(key="x", value="y")
        assert r.metadata is None

    def test_explicit_value_type(self):
        r = EnrichmentResult(key="email", value="a@b.com", value_type="email")
        assert r.value_type == "email"

    def test_explicit_metadata(self):
        r = EnrichmentResult(
            key="loc", value="Denver", value_type="location", metadata={"city": "Denver"}
        )
        assert r.metadata == {"city": "Denver"}


class TestEnrichmentWarning:
    """Tests for the EnrichmentWarning dataclass."""

    def test_fields(self):
        w = EnrichmentWarning(provider="acme", key="email", message="bad label")
        assert w.provider == "acme"
        assert w.key == "email"
        assert w.message == "bad label"


class TestEnrichmentRunResult:
    """Tests for the EnrichmentRunResult dataclass."""

    def test_defaults(self):
        r = EnrichmentRunResult(person_id="abc")
        assert r.person_id == "abc"
        assert r.attributes_saved == 0
        assert r.attributes_skipped == 0
        assert r.warnings == []

    def test_warnings_are_independent_per_instance(self):
        r1 = EnrichmentRunResult(person_id="a")
        r2 = EnrichmentRunResult(person_id="b")
        r1.warnings.append(EnrichmentWarning(provider="p", key="k", message="m"))
        assert r2.warnings == []


class TestPersonData:
    """Tests for PersonData dataclass."""

    def test_required_fields(self):
        p = PersonData(id="abc", name="Alice")
        assert p.id == "abc"
        assert p.name == "Alice"

    def test_optional_name_parts(self):
        p = PersonData(id="x", name="Alice", given_name="Alice", surname="Smith")
        assert p.given_name == "Alice"
        assert p.surname == "Smith"
        assert p.middle_name is None


class TestProviderABC:
    """Tests for the Provider abstract base class."""

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            Provider()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_enrich(self):
        class BadProvider(Provider):
            name = "bad"
            # missing enrich()

        with pytest.raises(TypeError):
            BadProvider()  # type: ignore[abstract]

    def test_valid_concrete_provider(self):
        class GoodProvider(Provider):
            name = "good"

            def enrich(self, person):
                return []

        p = GoodProvider()
        assert p.enrich(PersonData(id="x", name="Alice")) == []


class TestPackageExports:
    """Confirm all documented names are importable from the top-level package."""

    def test_attribute_value_exported(self):
        from src.core.enrichment import AttributeValue  # noqa: F401

    def test_concrete_types_exported(self):
        from src.core.enrichment import (
            DateAttributeValue,
            EmailAttributeValue,
            LocationAttributeValue,
            PhoneAttributeValue,
            PlatformUrlAttributeValue,
            TextAttributeValue,
            UrlAttributeValue,
        )

        assert EmailAttributeValue is not None
        assert PhoneAttributeValue is not None
        assert UrlAttributeValue is not None
        assert PlatformUrlAttributeValue is not None
        assert LocationAttributeValue is not None
        assert TextAttributeValue is not None
        assert DateAttributeValue is not None

    def test_vocabulary_constants_exported(self):
        from src.core.enrichment import LABELABLE_TYPES, VALUE_TYPE_CHOICES

        assert isinstance(VALUE_TYPE_CHOICES, list)
        assert isinstance(LABELABLE_TYPES, frozenset)

    def test_runner_and_registry_exported(self):
        from src.core.enrichment import EnrichmentRunner, ProviderRegistry

        assert EnrichmentRunner is not None
        assert ProviderRegistry is not None
