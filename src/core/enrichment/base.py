"""Core enrichment abstractions: Provider, EnrichmentResult, and run result types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import timedelta
from typing import ClassVar


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


class NoMatchSignal(Exception):
    """Raised by a provider to signal that no matching record was found.

    When raised from ``Provider.enrich()``, the runner writes an
    ``EnrichmentRun`` with ``status='no_match'`` and zero attributes saved.
    Unlike a normal exception, ``NoMatchSignal`` is not treated as a failure.
    """

    def __init__(self, message: str = "no match") -> None:
        super().__init__(message)


@dataclass
class PersonData:
    """Minimal read-only view of a person record passed to providers.

    Attributes:
        id: The person's primary key.
        name: Full display name.
        given_name: Given (first) name, if known.
        middle_name: Middle name, if known.
        surname: Family name, if known.
        existing_attributes: Attributes already persisted for this person.
            Each dict has keys: key (str), value (str), value_type (str),
            source (str). Populated by EnrichmentRunner from the DB before
            each execution round so that providers can inspect prior enrichment
            and so that can_run() checks reflect newly-written attributes.
    """

    id: str
    name: str
    given_name: str | None = None
    middle_name: str | None = None
    surname: str | None = None
    existing_attributes: list[dict] = field(default_factory=list)

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
    attributes_refreshed: int = 0
    warnings: list[EnrichmentWarning] = field(default_factory=list)


class Provider(ABC):
    """Abstract base class for enrichment providers.

    Subclasses **must** declare ``name``, and **should** override
    ``output_keys`` and ``dependencies`` with their own list literals —
    never mutate the class-level defaults, as they are shared across all
    subclasses that do not override them.
    """

    #: Unique identifier for this provider. Must be set by each subclass.
    name: str

    #: Attribute keys this provider may produce. Used to build the dependency
    #: graph. Subclasses must override with a fresh list, e.g.
    #: ``output_keys = ["wikidata_qid", "wikidata_url"]``.
    output_keys: ClassVar[list[str]] = []

    #: Dependencies this provider requires. Empty means no prerequisites.
    #: Subclasses must override with a fresh list, e.g.
    #: ``dependencies = [Dependency("wikidata_qid")]``.
    dependencies: ClassVar[list[Dependency]] = []

    #: How long before a completed enrichment run is considered stale and
    #: eligible for re-enrichment. Defaults to 7 days.
    refresh_interval: ClassVar[timedelta] = timedelta(days=7)

    #: ExternalPlatform slugs this provider requires to be active before it
    #: can run.  The runner checks these against the active platform set at
    #: the start of each run; any missing slug causes the provider to be
    #: skipped (status='skipped') rather than failing at persist time.
    #: Subclasses must override with a fresh list, e.g.
    #: ``required_platforms: ClassVar[list[str]] = ["wikidata"]``.
    required_platforms: ClassVar[list[str]] = []

    def can_run(
        self,
        existing_attribute_keys: set[str],
        active_platforms: set[str] | None = None,
    ) -> bool:
        """Return True if all skip_if_absent dependencies are satisfied
        and all required_platforms are active.

        Args:
            existing_attribute_keys: Attribute keys already persisted for this person.
            active_platforms: Set of active ExternalPlatform slugs.  When
                ``None`` (default) the platform check is skipped — this
                preserves backward compatibility for callers that don't yet
                supply a platform set.
        """
        deps_ok = all(
            dep.attribute_key in existing_attribute_keys
            for dep in self.dependencies
            if dep.skip_if_absent
        )
        if not deps_ok:
            return False
        if active_platforms is not None:
            for slug in self.required_platforms:
                if slug not in active_platforms:
                    return False
        return True

    @abstractmethod
    def enrich(self, person: PersonData, **kwargs: object) -> list[EnrichmentResult]:
        """Return a list of enrichment results for the given person.

        Subclasses may declare specific keyword arguments (e.g.
        ``confirmed_wikidata_qid``) for provider-specific behaviour.
        The ``**kwargs`` signature here ensures that any extra kwargs
        forwarded by the runner do not cause a ``TypeError`` in providers
        that do not use them.
        """
        ...
