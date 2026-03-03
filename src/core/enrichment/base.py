"""Core enrichment abstractions: Provider, EnrichmentResult, and run result types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class PersonData:
    """Minimal read-only view of a person record passed to providers."""

    id: str
    name: str
    given_name: str | None = None
    middle_name: str | None = None
    surname: str | None = None


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

    @abstractmethod
    def enrich(self, person: PersonData) -> list[EnrichmentResult]:
        """Return a list of enrichment results for the given person."""
        ...
