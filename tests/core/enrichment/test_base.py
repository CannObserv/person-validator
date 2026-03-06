"""Tests for base enrichment dataclasses, Provider ABC, and package exports."""

from datetime import timedelta

import pytest

from src.core.enrichment.base import (
    CircularDependencyError,
    Dependency,
    EnrichmentResult,
    EnrichmentRunResult,
    EnrichmentWarning,
    NoMatchSignal,
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

    def test_existing_attributes_defaults_to_empty(self):
        p = PersonData(id="x", name="Alice")
        assert p.existing_attributes == []

    def test_existing_attributes_are_independent_per_instance(self):
        p1 = PersonData(id="a", name="Alice")
        p2 = PersonData(id="b", name="Bob")
        p1.existing_attributes.append(
            {"key": "foo", "value": "bar", "value_type": "text", "source": "s"}
        )
        assert p2.existing_attributes == []

    def test_attribute_keys_returns_set_of_keys(self):
        p = PersonData(
            id="x",
            name="Alice",
            existing_attributes=[
                {"key": "wikidata_qid", "value": "Q42", "value_type": "text", "source": "wikidata"},
                {
                    "key": "wikidata_url",
                    "value": "https://wikidata.org/wiki/Q42",
                    "value_type": "url",
                    "source": "wikidata",
                },
            ],
        )
        assert p.attribute_keys() == {"wikidata_qid", "wikidata_url"}

    def test_attribute_keys_empty_when_no_attributes(self):
        p = PersonData(id="x", name="Alice")
        assert p.attribute_keys() == set()


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


class TestDependency:
    """Tests for the Dependency dataclass."""

    def test_required_field(self):
        d = Dependency(attribute_key="wikidata_qid")
        assert d.attribute_key == "wikidata_qid"

    def test_skip_if_absent_defaults_true(self):
        d = Dependency(attribute_key="wikidata_qid")
        assert d.skip_if_absent is True

    def test_skip_if_absent_can_be_false(self):
        d = Dependency(attribute_key="wikidata_qid", skip_if_absent=False)
        assert d.skip_if_absent is False


class TestCircularDependencyError:
    """Tests for CircularDependencyError."""

    def test_is_exception(self):
        assert issubclass(CircularDependencyError, Exception)

    def test_can_raise(self):
        with pytest.raises(CircularDependencyError):
            raise CircularDependencyError("cycle detected")


class TestNoMatchSignal:
    """Tests for NoMatchSignal."""

    def test_is_exception(self):
        assert issubclass(NoMatchSignal, Exception)

    def test_can_raise(self):
        with pytest.raises(NoMatchSignal):
            raise NoMatchSignal()

    def test_default_message(self):
        exc = NoMatchSignal()
        assert str(exc) == "no match"

    def test_custom_message(self):
        exc = NoMatchSignal("no results for 'Ada Lovelace'")
        assert "Ada Lovelace" in str(exc)


class TestProviderDependenciesAndOutputKeys:
    """Tests for Provider.dependencies, output_keys, can_run."""

    def _make_provider(self, name, deps=None, outputs=None):
        class _P(Provider):
            dependencies = deps or []
            output_keys = outputs or []

            def enrich(self, person):
                return []

        _P.name = name
        return _P()

    def test_dependencies_defaults_to_empty(self):
        p = self._make_provider("p")
        assert p.dependencies == []

    def test_output_keys_defaults_to_empty(self):
        p = self._make_provider("p")
        assert p.output_keys == []

    def test_can_run_no_dependencies(self):
        p = self._make_provider("p")
        assert p.can_run(set()) is True
        assert p.can_run({"anything"}) is True

    def test_can_run_satisfied_dependency(self):
        p = self._make_provider("p", deps=[Dependency(attribute_key="wikidata_qid")])
        assert p.can_run({"wikidata_qid", "other"}) is True

    def test_can_run_unsatisfied_skip_if_absent_true(self):
        p = self._make_provider("p", deps=[Dependency(attribute_key="wikidata_qid")])
        assert p.can_run(set()) is False
        assert p.can_run({"something_else"}) is False

    def test_can_run_unsatisfied_skip_if_absent_false(self):
        """When skip_if_absent=False, missing dep does NOT block execution."""
        p = self._make_provider(
            "p", deps=[Dependency(attribute_key="wikidata_qid", skip_if_absent=False)]
        )
        assert p.can_run(set()) is True

    def test_can_run_multiple_deps_all_satisfied(self):
        p = self._make_provider(
            "p",
            deps=[
                Dependency(attribute_key="a"),
                Dependency(attribute_key="b"),
            ],
        )
        assert p.can_run({"a", "b"}) is True

    def test_can_run_multiple_deps_one_missing(self):
        p = self._make_provider(
            "p",
            deps=[
                Dependency(attribute_key="a"),
                Dependency(attribute_key="b"),
            ],
        )
        assert p.can_run({"a"}) is False

    def test_can_run_mixed_skip_if_absent(self):
        """Only skip_if_absent=True deps gate execution."""
        p = self._make_provider(
            "p",
            deps=[
                Dependency(attribute_key="a", skip_if_absent=True),
                Dependency(attribute_key="b", skip_if_absent=False),
            ],
        )
        # a present, b absent → should run (b is optional)
        assert p.can_run({"a"}) is True
        # a absent, b present → should not run (a is required)
        assert p.can_run({"b"}) is False

    def test_output_keys_and_dependencies_are_class_vars_not_shared(self):
        """Subclasses that override output_keys/dependencies don't pollute each other."""

        class P1(Provider):
            name = "p1"
            output_keys = ["key_a"]
            dependencies = [Dependency("dep_a")]

            def enrich(self, person):
                return []

        class P2(Provider):
            name = "p2"
            output_keys = ["key_b"]
            dependencies = []

            def enrich(self, person):
                return []

        assert P1.output_keys == ["key_a"]
        assert P2.output_keys == ["key_b"]
        assert P1.dependencies == [Dependency("dep_a")]
        assert P2.dependencies == []

    def test_refresh_interval_defaults_to_seven_days(self):
        p = self._make_provider("p")
        assert p.refresh_interval == timedelta(days=7)

    def test_refresh_interval_can_be_overridden(self):
        class FastProvider(Provider):
            name = "fast"
            refresh_interval = timedelta(hours=1)

            def enrich(self, person):
                return []

        assert FastProvider().refresh_interval == timedelta(hours=1)

    def test_required_platforms_defaults_empty(self):
        p = self._make_provider("p")
        assert p.required_platforms == []

    def test_can_run_passes_when_required_platform_active(self):
        class PlatformProvider(Provider):
            name = "pp"
            required_platforms: list[str] = ["wikidata"]

            def enrich(self, person):
                return []

        p = PlatformProvider()
        assert p.can_run(set(), active_platforms={"wikidata", "other"}) is True

    def test_can_run_fails_when_required_platform_missing(self):
        class PlatformProvider(Provider):
            name = "pp2"
            required_platforms: list[str] = ["wikidata"]

            def enrich(self, person):
                return []

        p = PlatformProvider()
        assert p.can_run(set(), active_platforms=set()) is False
        assert p.can_run(set(), active_platforms={"wikipedia"}) is False

    def test_can_run_skips_platform_check_when_none(self):
        """Backward compatibility: no platform check when active_platforms is None."""

        class PlatformProvider(Provider):
            name = "pp3"
            required_platforms: list[str] = ["wikidata"]

            def enrich(self, person):
                return []

        p = PlatformProvider()
        # No platform set supplied — check is skipped, deps still determine result.
        assert p.can_run(set(), active_platforms=None) is True

    def test_can_run_deps_and_platform_both_checked(self):
        """Both dependency and platform checks must pass."""

        class FullProvider(Provider):
            name = "fp"
            dependencies = [Dependency(attribute_key="wikidata_qid")]
            required_platforms: list[str] = ["wikidata"]

            def enrich(self, person):
                return []

        p = FullProvider()
        # Platform active but dep missing
        assert p.can_run(set(), active_platforms={"wikidata"}) is False
        # Dep satisfied but platform missing
        assert p.can_run({"wikidata_qid"}, active_platforms=set()) is False
        # Both satisfied
        assert p.can_run({"wikidata_qid"}, active_platforms={"wikidata"}) is True


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

    def test_dependency_and_error_exported(self):
        from src.core.enrichment import CircularDependencyError, Dependency, NoMatchSignal

        assert Dependency is not None
        assert CircularDependencyError is not None
        assert NoMatchSignal is not None
