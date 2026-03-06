"""Core enrichment abstractions: Provider, EnrichmentResult, and run result types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Dependency:
    """Declares that a provider requires a specific attribute key to be present.

    Args:
        attribute_key: The PersonAttribute.key value that must exist for this
            person before this provider can run.
        skip_if_absent: If True (default), the provider is skipped entirely
            when the dependency attribute is not present. If False, the provider
            still runs; it must handle absence gracefully via the
            existing_attributes field on PersonData.
    """

    attribute_key: str
    skip_if_absent: bool = True


class CircularDependencyError(Exception):
    """Raised when provider dependencies contain a cycle."""


@dataclass
class PersonData:
    """Minimal read-only view of a person record passed to providers."""

    id: str
    name: str
    given_name: str | None = None
    middle_name: str | None = None
    surname: str | None = None
    existing_attributes: list[dict] = field(default_factory=list)
    """Each dict has keys: key (str), value (str), value_type (str), source (str).

    Populated by EnrichmentRunner from the DB before running providers.
    """

    def attribute_keys(self) -> set[str]:
        """Return the set of attribute keys currently on this person."""
        return {a["key"] for a in self.existing_attributes}


@dataclass
class EnrichmentResult:
    """A single attribute value returned by an enrichment provider."""

    key: str
    value: str
    value_type: str = "text"
    confidence: float = 1.0
    metadata: dict | None = None


@dataclass
class EnrichmentWarning:
    """A non-fatal warning produced during an enrichment run.

    Warnings are generated when a label slug or platform slug is not in
    the active controlled vocabulary. The offending value is stripped
    but the attribute is still persisted.
    """

    provider: str
    key: str
    message: str


@dataclass
class EnrichmentRunResult:
    """Summary of a completed enrichment run for a single person."""

    person_id: str
    attributes_saved: int = 0
    attributes_skipped: int = 0
    warnings: list[EnrichmentWarning] = field(default_factory=list)


class Provider(ABC):
    """Abstract base class for enrichment providers."""

    #: Unique identifier for this provider. Must be set by each subclass.
    name: str

    #: Attribute keys this provider may produce. Used to build the dependency graph.
    output_keys: list[str] = []

    #: Dependencies this provider requires. Empty means no prerequisites.
    dependencies: list[Dependency] = []

    def can_run(self, existing_attribute_keys: set[str]) -> bool:
        """Return True if all skip_if_absent dependencies are satisfied."""
        return all(
            dep.attribute_key in existing_attribute_keys
            for dep in self.dependencies
            if dep.skip_if_absent
        )

    @abstractmethod
    def enrich(self, person: PersonData) -> list[EnrichmentResult]:
        """Return a list of enrichment results for the given person."""
        ...
