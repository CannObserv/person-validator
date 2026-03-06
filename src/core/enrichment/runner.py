"""Enrichment runner: orchestrates providers, validates results, persists attributes."""

from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.db import close_old_connections
from django.utils import timezone
from pydantic import TypeAdapter, ValidationError

from src.core.enrichment.attribute_types import (
    LABELABLE_TYPES,
    AttributeValue,
    LocationAttributeValue,
    PlatformUrlAttributeValue,
)
from src.core.enrichment.base import (
    CircularDependencyError,
    EnrichmentResult,
    EnrichmentRunResult,
    EnrichmentWarning,
    PersonData,
    Provider,
)
from src.core.enrichment.registry import ProviderRegistry
from src.core.logging import get_logger

# NOTE: src.web.persons.models imports src.core.enrichment (for VALUE_TYPE_CHOICES),
# creating a circular dependency at module level. All imports of Django models in this
# module use deferred inline imports inside functions to break the cycle.

logger = get_logger(__name__)

# Module-level adapter — TypeAdapter construction is non-trivial; build once.
_attribute_value_adapter = TypeAdapter(AttributeValue)


def _resolve_execution_rounds(providers: list[Provider]) -> list[list[Provider]]:
    """Topological sort of providers by dependency graph.

    Returns a list of rounds. Providers within a round have no inter-dependencies
    and can run in parallel. Providers in round N+1 depend on output from round N.

    Uses Kahn's algorithm (BFS-based topological sort).

    Raises CircularDependencyError if a dependency cycle is detected.
    """
    if not providers:
        return []

    # Map from output_key -> list of providers that produce it.
    key_to_producers: dict[str, list[Provider]] = defaultdict(list)
    for p in providers:
        for key in p.output_keys:
            key_to_producers[key].append(p)

    # Build adjacency list and in-degree count.
    # Edge: producer -> consumer (producer must run before consumer).
    adj: dict[str, set[str]] = defaultdict(set)  # provider.name -> set of downstream provider names
    in_degree: dict[str, int] = {p.name: 0 for p in providers}
    provider_by_name: dict[str, Provider] = {p.name: p for p in providers}

    for consumer in providers:
        for dep in consumer.dependencies:
            producers = key_to_producers.get(dep.attribute_key, [])
            for producer in producers:
                if producer.name != consumer.name and consumer.name not in adj[producer.name]:
                    adj[producer.name].add(consumer.name)
                    in_degree[consumer.name] += 1
                elif producer.name == consumer.name:
                    # Self-cycle
                    raise CircularDependencyError(
                        f"Provider '{consumer.name}' depends on its own output"
                        f" key '{dep.attribute_key}'"
                    )

    # Kahn's algorithm
    queue: deque[Provider] = deque(p for p in providers if in_degree[p.name] == 0)
    rounds: list[list[Provider]] = []
    visited_count = 0

    while queue:
        # All items currently in the queue form one parallel round.
        current_round = list(queue)
        queue.clear()
        rounds.append(current_round)
        visited_count += len(current_round)

        next_round_names: set[str] = set()
        for p in current_round:
            for downstream_name in adj[p.name]:
                in_degree[downstream_name] -= 1
                if in_degree[downstream_name] == 0:
                    next_round_names.add(downstream_name)

        for name in next_round_names:
            queue.append(provider_by_name[name])

    if visited_count != len(providers):
        raise CircularDependencyError(
            "Circular dependency detected among providers: "
            + ", ".join(name for name, deg in in_degree.items() if deg > 0)
        )

    return rounds


def _load_active_labels(value_type: str) -> set[str]:
    """Return the set of active label slugs for *value_type* from the DB."""
    from src.web.persons.models import AttributeLabel  # noqa: PLC0415 (circular — see module note)

    return set(
        AttributeLabel.objects.filter(value_type=value_type, is_active=True).values_list(
            "slug", flat=True
        )
    )


def _load_active_platforms() -> set[str]:
    """Return the set of active external platform slugs from the DB."""
    from src.web.persons.models import (
        ExternalPlatform,  # noqa: PLC0415 (circular — see module note)
    )

    return set(ExternalPlatform.objects.filter(is_active=True).values_list("slug", flat=True))


def _load_existing_attributes(person_id: str) -> list[dict]:
    """Load all current PersonAttribute rows for *person_id* from the DB.

    Returns a list of dicts with keys: key, value, value_type, source.
    """
    from src.web.persons.models import PersonAttribute  # noqa: PLC0415 (circular — see module note)

    return list(
        PersonAttribute.objects.filter(person_id=person_id).values(
            "key", "value", "value_type", "source"
        )
    )


def _validate_result(result: EnrichmentResult) -> AttributeValue | None:
    """Validate an EnrichmentResult via the AttributeValue discriminated union.

    Returns the parsed model on success, or None on failure.
    """
    payload = {
        "type": result.value_type,
        "value": result.value,
        "confidence": result.confidence,
    }
    if result.metadata:
        payload.update(result.metadata)
    try:
        return _attribute_value_adapter.validate_python(payload)
    except ValidationError as exc:
        logger.warning("Attribute validation failed: %s", exc)
        return None


def _strip_invalid_labels(
    validated: AttributeValue,
    provider_name: str,
    key: str,
    active_labels: set[str],
    warnings: list[EnrichmentWarning],
) -> list[str]:
    """Strip unknown label slugs and record a warning per stripped slug.

    Returns the cleaned label list (may be empty).
    """
    raw_labels: list[str] = getattr(validated, "label", []) or []
    if not raw_labels:
        return []

    clean: list[str] = []
    for slug in raw_labels:
        if slug in active_labels:
            clean.append(slug)
        else:
            msg = f"Unknown label '{slug}' for value_type '{validated.type}' — stripped"
            logger.warning("[%s/%s] %s", provider_name, key, msg)
            warnings.append(EnrichmentWarning(provider=provider_name, key=key, message=msg))
    return clean


def _strip_invalid_platform(
    validated: PlatformUrlAttributeValue,
    provider_name: str,
    key: str,
    active_platforms: set[str],
    warnings: list[EnrichmentWarning],
) -> str | None:
    """Strip unknown platform slug and record a warning. Returns cleaned value."""
    if validated.platform is None:
        return None
    if validated.platform in active_platforms:
        return validated.platform
    msg = f"Unknown platform '{validated.platform}' for platform_url — platform field cleared"
    logger.warning("[%s/%s] %s", provider_name, key, msg)
    warnings.append(EnrichmentWarning(provider=provider_name, key=key, message=msg))
    return None


def _build_metadata(
    validated: AttributeValue,
    clean_labels: list[str],
    clean_platform: str | None = None,
) -> dict | None:
    """Build the metadata dict to persist for a validated attribute."""
    meta: dict = {}

    if clean_labels:
        meta["label"] = clean_labels

    if isinstance(validated, PlatformUrlAttributeValue):
        if clean_platform is not None:
            meta["platform"] = clean_platform

    elif isinstance(validated, LocationAttributeValue):
        # Derive location metadata fields dynamically from the model to avoid
        # manual field list maintenance.
        location_fields = validated.model_dump(exclude={"type", "value", "label", "confidence"})
        meta.update({k: v for k, v in location_fields.items() if v is not None})

    return meta or None


def _persist_attribute(
    person_id: str,
    provider_name: str,
    result: EnrichmentResult,
    validated: AttributeValue,
    clean_labels: list[str],
    clean_platform: str | None = None,
) -> None:
    """Persist a single validated EnrichmentResult to the database."""
    from src.web.persons.models import PersonAttribute  # noqa: PLC0415 (circular — see module note)

    meta = _build_metadata(validated, clean_labels, clean_platform)

    # Coerce AnyUrl to string for storage.
    value_str = str(validated.value)

    PersonAttribute.objects.create(
        person_id=person_id,
        source=provider_name,
        key=result.key,
        value=value_str,
        value_type=result.value_type,
        metadata=meta,
        confidence=result.confidence,
    )


def _run_single_provider_in_thread(
    provider: Provider,
    person: PersonData,
    triggered_by: str,
    label_cache: dict[str, set[str]],
    platform_cache: set[str],
) -> EnrichmentRunResult:
    """Thread-safe wrapper: ensures DB connections are fresh per thread."""
    close_old_connections()
    try:
        return _run_single_provider(provider, person, triggered_by, label_cache, platform_cache)
    finally:
        close_old_connections()


def _run_single_provider(
    provider: Provider,
    person: PersonData,
    triggered_by: str,
    label_cache: dict[str, set[str]],
    platform_cache: set[str],
) -> EnrichmentRunResult:
    """Run one provider against a person and persist results.

    Creates and updates an EnrichmentRun audit record. Returns the per-provider
    EnrichmentRunResult (not the aggregate).
    """
    from src.web.persons.models import EnrichmentRun  # noqa: PLC0415 (circular — see module note)

    provider_saved = 0
    provider_skipped = 0
    provider_warnings: list[EnrichmentWarning] = []
    db_run: EnrichmentRun | None = None

    try:
        db_run = EnrichmentRun.objects.create(
            person_id=person.id,
            provider=provider.name,
            status="running",
            triggered_by=triggered_by,
            started_at=timezone.now(),
        )

        results = provider.enrich(person)

        for result in results:
            validated = _validate_result(result)
            if validated is None:
                logger.warning(
                    "Skipping invalid attribute '%s' from provider '%s'",
                    result.key,
                    provider.name,
                )
                provider_skipped += 1
                continue

            clean_labels: list[str] = []
            if result.value_type in LABELABLE_TYPES:
                clean_labels = _strip_invalid_labels(
                    validated,
                    provider.name,
                    result.key,
                    label_cache[result.value_type],
                    provider_warnings,
                )

            clean_platform: str | None = None
            if isinstance(validated, PlatformUrlAttributeValue):
                clean_platform = _strip_invalid_platform(
                    validated,
                    provider.name,
                    result.key,
                    platform_cache,
                    provider_warnings,
                )

            try:
                _persist_attribute(
                    person.id,
                    provider.name,
                    result,
                    validated,
                    clean_labels,
                    clean_platform,
                )
                provider_saved += 1
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to persist attribute '%s' from provider '%s'",
                    result.key,
                    provider.name,
                )
                provider_skipped += 1

        db_run.status = "completed"
        db_run.attributes_saved = provider_saved
        db_run.attributes_skipped = provider_skipped
        db_run.warnings = [w.__dict__ for w in provider_warnings]

    except Exception as exc:  # noqa: BLE001
        logger.exception("Provider '%s' raised an exception", provider.name)
        if db_run is not None:
            db_run.status = "failed"
            db_run.error = str(exc)

    finally:
        if db_run is not None:
            db_run.completed_at = timezone.now()
            db_run.save()

    return EnrichmentRunResult(
        person_id=person.id,
        attributes_saved=provider_saved,
        attributes_skipped=provider_skipped,
        warnings=provider_warnings,
    )


def _log_skipped_provider(provider: Provider, person: PersonData, triggered_by: str) -> None:
    """Create an EnrichmentRun with status='skipped' for a provider that cannot run."""
    from src.web.persons.models import EnrichmentRun  # noqa: PLC0415 (circular — see module note)

    now = timezone.now()
    EnrichmentRun.objects.create(
        person_id=person.id,
        provider=provider.name,
        status="skipped",
        triggered_by=triggered_by,
        started_at=now,
        completed_at=now,
    )


class EnrichmentRunner:
    """Runs all enabled providers against a person and persists results.

    Providers are sorted into execution rounds by their dependency graph
    (topological sort). Providers within a round run in parallel via
    ThreadPoolExecutor. Between rounds, existing_attributes on PersonData
    is refreshed from the DB so downstream can_run() checks are accurate.

    Usage::

        runner = EnrichmentRunner(registry)
        results = runner.run(person_data)  # returns dict[str, EnrichmentRunResult]
    """

    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry

    def run(
        self,
        person: PersonData,
        *,
        triggered_by: str = "manual",
        provider_names: list[str] | None = None,
    ) -> dict[str, EnrichmentRunResult]:
        """Run providers against a person.

        Args:
            person: The person to enrich.
            triggered_by: Label for the audit log (e.g. "manual", "admin").
            provider_names: If given, only these providers are run. None = all enabled.

        Returns:
            A dict mapping provider name to EnrichmentRunResult.

        Notes:
            - Provider failures are caught and logged; other providers still run.
            - Invalid attribute values (Pydantic failure) are skipped.
            - Unknown label slugs are stripped with a warning.
            - Unknown platform slugs are stripped with a warning.
            - An EnrichmentRun audit record is created per provider.
            - Providers whose can_run() returns False get status='skipped'.
        """
        # Select providers.
        candidates = self._registry.enabled_providers()
        if provider_names is not None:
            name_set = set(provider_names)
            candidates = [p for p in candidates if p.name in name_set]

        # Load vocab sets once per run.
        label_cache: dict[str, set[str]] = {vt: _load_active_labels(vt) for vt in LABELABLE_TYPES}
        platform_cache: set[str] = _load_active_platforms()

        # Topological sort into rounds.
        rounds = _resolve_execution_rounds(candidates)

        results: dict[str, EnrichmentRunResult] = {}

        for round_providers in rounds:
            # Refresh existing_attributes before each round so can_run() is current.
            person.existing_attributes = _load_existing_attributes(person.id)

            runnable = [p for p in round_providers if p.can_run(person.attribute_keys())]
            skipped = [p for p in round_providers if not p.can_run(person.attribute_keys())]

            for provider in skipped:
                logger.info("Provider '%s' skipped: unmet dependencies", provider.name)
                _log_skipped_provider(provider, person, triggered_by)
                results[provider.name] = EnrichmentRunResult(
                    person_id=person.id,
                    attributes_saved=0,
                    attributes_skipped=0,
                    warnings=[],
                )

            if len(runnable) <= 1:
                # Single provider: run inline to avoid thread overhead and SQLite
                # locking issues (SQLite cannot handle concurrent writes from
                # multiple threads when a test transaction is open).
                for provider in runnable:
                    try:
                        run_result = _run_single_provider(
                            provider, person, triggered_by, label_cache, platform_cache
                        )
                        results[provider.name] = run_result
                    except Exception:  # noqa: BLE001
                        logger.exception("Provider '%s' failed", provider.name)
                        results[provider.name] = EnrichmentRunResult(
                            person_id=person.id,
                            attributes_saved=0,
                            attributes_skipped=0,
                            warnings=[],
                        )
            else:
                max_workers = min(len(runnable), 8)
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(
                            _run_single_provider_in_thread,
                            provider,
                            person,
                            triggered_by,
                            label_cache,
                            platform_cache,
                        ): provider
                        for provider in runnable
                    }
                    for future in as_completed(futures):
                        provider = futures[future]
                        try:
                            run_result = future.result()
                            results[provider.name] = run_result
                        except Exception:  # noqa: BLE001
                            logger.exception("Provider '%s' failed in executor", provider.name)
                            results[provider.name] = EnrichmentRunResult(
                                person_id=person.id,
                                attributes_saved=0,
                                attributes_skipped=0,
                                warnings=[],
                            )

        return results
