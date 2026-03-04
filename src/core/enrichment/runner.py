"""Enrichment runner: orchestrates providers, validates results, persists attributes."""

import logging

from pydantic import TypeAdapter, ValidationError

from src.core.enrichment.attribute_types import (
    LABELABLE_TYPES,
    AttributeValue,
    LocationAttributeValue,
    PlatformUrlAttributeValue,
)
from src.core.enrichment.base import (
    EnrichmentResult,
    EnrichmentRunResult,
    EnrichmentWarning,
    PersonData,
)
from src.core.enrichment.registry import ProviderRegistry

logger = logging.getLogger(__name__)

# Module-level adapter — TypeAdapter construction is non-trivial; build once.
_attribute_value_adapter = TypeAdapter(AttributeValue)


def _load_active_labels(value_type: str) -> set[str]:
    """Return the set of active label slugs for *value_type* from the DB."""
    from src.web.persons.models import AttributeLabel  # noqa: PLC0415

    return set(
        AttributeLabel.objects.filter(value_type=value_type, is_active=True).values_list(
            "slug", flat=True
        )
    )


def _load_active_platforms() -> set[str]:
    """Return the set of active social platform slugs from the DB."""
    from src.web.persons.models import SocialPlatform  # noqa: PLC0415

    return set(SocialPlatform.objects.filter(is_active=True).values_list("slug", flat=True))


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
    from src.web.persons.models import PersonAttribute  # noqa: PLC0415

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


class EnrichmentRunner:
    """Runs all enabled providers against a person and persists results.

    Usage::

        runner = EnrichmentRunner(registry)
        run_result = runner.run(person_data)
    """

    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry

    def run(self, person: PersonData) -> EnrichmentRunResult:
        """Run all enabled providers and return an EnrichmentRunResult.

        - Provider failures are caught and logged; other providers still run.
        - Invalid attribute values (Pydantic failure) are skipped.
        - Unknown label slugs are stripped with a warning.
        - Unknown platform slugs are stripped with a warning.
        """
        run_result = EnrichmentRunResult(person_id=person.id)

        # Load vocab sets once per run to avoid per-attribute DB queries.
        label_cache: dict[str, set[str]] = {vt: _load_active_labels(vt) for vt in LABELABLE_TYPES}
        platform_cache: set[str] = _load_active_platforms()

        for provider in self._registry.enabled_providers():
            try:
                results = provider.enrich(person)
            except Exception:  # noqa: BLE001
                logger.exception("Provider '%s' raised an exception", provider.name)
                continue

            for result in results:
                validated = _validate_result(result)
                if validated is None:
                    logger.warning(
                        "Skipping invalid attribute '%s' from provider '%s'",
                        result.key,
                        provider.name,
                    )
                    run_result.attributes_skipped += 1
                    continue

                # Strip unknown labels using the pre-loaded cache.
                clean_labels: list[str] = []
                if result.value_type in LABELABLE_TYPES:
                    clean_labels = _strip_invalid_labels(
                        validated,
                        provider.name,
                        result.key,
                        label_cache[result.value_type],
                        run_result.warnings,
                    )

                # Strip unknown platform using the pre-loaded cache.
                clean_platform: str | None = None
                if isinstance(validated, PlatformUrlAttributeValue):
                    clean_platform = _strip_invalid_platform(
                        validated,
                        provider.name,
                        result.key,
                        platform_cache,
                        run_result.warnings,
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
                    run_result.attributes_saved += 1
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Failed to persist attribute '%s' from provider '%s'",
                        result.key,
                        provider.name,
                    )
                    run_result.attributes_skipped += 1

        return run_result
