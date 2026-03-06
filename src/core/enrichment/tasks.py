"""Enrichment task utilities — synchronous functions invoked by signals and admin actions.

These are deliberately synchronous (no Celery). A future issue may add async dispatch;
for now they execute inline in the caller's request/signal cycle.
"""

from src.core.logging import get_logger

logger = get_logger(__name__)


def run_enrichment_for_person(
    *,
    person_id: str,
    triggered_by: str,
    confirmed_wikidata_qid: str | None = None,
    force_rescore: bool = False,
) -> None:
    """Build a PersonData snapshot and run the full EnrichmentRunner for a person.

    Args:
        person_id: Primary key of the Person record.
        triggered_by: Audit label written to EnrichmentRun.triggered_by
            (e.g. "adjudication", "manual").
        confirmed_wikidata_qid: When set, the ``wikidata_qid`` attribute is injected
            into PersonData.existing_attributes before providers run so that
            downstream providers whose dependency is ``wikidata_qid`` are included
            in the execution graph even if the attribute has not yet been persisted.
        force_rescore: When True, any existing ``wikidata_qid`` attribute is stripped
            from existing_attributes before providers run, forcing WikidataProvider
            to perform a fresh search instead of re-using the previously linked QID.

    Raises:
        Person.DoesNotExist: If no person with the given ID exists.
    """
    # Deferred to avoid AppRegistryNotReady at import time.
    from src.core.enrichment.base import PersonData  # noqa: PLC0415
    from src.core.enrichment.registry import ProviderRegistry  # noqa: PLC0415
    from src.core.enrichment.runner import (  # noqa: PLC0415
        EnrichmentRunner,
        _load_existing_attributes,
    )
    from src.web.persons.models import Person  # noqa: PLC0415

    person_obj = Person.objects.get(pk=person_id)

    existing = _load_existing_attributes(person_id)

    if force_rescore:
        existing = [a for a in existing if a.get("key") != "wikidata_qid"]

    if confirmed_wikidata_qid:
        # Inject a synthetic attribute so downstream providers see wikidata_qid
        # immediately, even before WikidataProvider has had a chance to persist it.
        existing = [a for a in existing if a.get("key") != "wikidata_qid"] + [
            {
                "key": "wikidata_qid",
                "value": confirmed_wikidata_qid,
                "value_type": "text",
                "source": "adjudication",
            }
        ]

    person_data = PersonData(
        id=str(person_obj.pk),
        name=person_obj.name,
        given_name=person_obj.given_name,
        middle_name=person_obj.middle_name,
        surname=person_obj.surname,
        existing_attributes=existing,
    )

    # Build a registry containing all providers registered at call time.
    # WikidataProvider and other concrete providers are registered here.
    # For now, build a fresh registry on each call; a future issue may
    # introduce a module-level singleton populated at app startup.
    registry = ProviderRegistry()
    if not registry.enabled_providers():
        logger.warning(
            "run_enrichment_for_person: no providers registered; enrichment is a no-op",
            extra={"person_id": person_id, "triggered_by": triggered_by},
        )
    runner = EnrichmentRunner(registry)

    try:
        runner.run(person_data, triggered_by=triggered_by)
    except Exception:
        logger.exception(
            "run_enrichment_for_person failed",
            extra={"person_id": person_id, "triggered_by": triggered_by},
        )
        raise


def bump_wikidata_confidence(
    *,
    person_id: str,
    reviewed_by_id: int | None,
) -> None:
    """Raise confidence on existing Wikidata-sourced attributes from 0.75 to 0.95.

    Called when an admin confirms an auto-linked WikidataCandidateReview.  Updates
    all ``PersonAttribute`` rows where ``source='wikidata'`` and ``confidence``
    is approximately 0.75 for the given person.

    Args:
        person_id: Primary key of the Person record.
        reviewed_by_id: PK of the User who confirmed the review (logged only).
    """
    from django.utils import timezone  # noqa: PLC0415

    from src.web.persons.models import PersonAttribute  # noqa: PLC0415

    updated = PersonAttribute.objects.filter(
        person_id=person_id,
        source="wikidata",
        confidence__gte=0.74,
        confidence__lte=0.76,
    ).update(confidence=0.95, updated_at=timezone.now())

    logger.info(
        "Bumped Wikidata attribute confidence",
        extra={
            "person_id": person_id,
            "updated_count": updated,
            "reviewed_by_id": reviewed_by_id,
        },
    )


def rollback_wikidata_autolink(*, person_id: str) -> None:
    """Delete Wikidata-sourced attributes/names written at auto-link confidence and re-queue.

    Called when an admin rejects an ``auto_linked`` WikidataCandidateReview.  Removes
    all ``PersonAttribute`` rows where ``source='wikidata'`` and ``confidence`` is
    approximately 0.75, and ``PersonName`` rows where ``source='wikidata'`` and
    ``confidence`` is approximately 0.70.  Then re-triggers enrichment with
    ``force_rescore=True`` so WikidataProvider performs a fresh search instead of
    immediately re-linking to the just-rejected QID.

    Args:
        person_id: Primary key of the Person record.
    """
    from src.web.persons.models import PersonAttribute, PersonName  # noqa: PLC0415

    deleted_attrs, _ = PersonAttribute.objects.filter(
        person_id=person_id,
        source="wikidata",
        confidence__gte=0.74,
        confidence__lte=0.76,
    ).delete()

    deleted_names, _ = PersonName.objects.filter(
        person_id=person_id,
        source="wikidata",
        confidence__gte=0.69,
        confidence__lte=0.71,
    ).delete()

    logger.info(
        "Rolled back Wikidata auto-link",
        extra={
            "person_id": person_id,
            "deleted_attributes": deleted_attrs,
            "deleted_names": deleted_names,
        },
    )

    run_enrichment_for_person(
        person_id=person_id,
        triggered_by="rollback",
        force_rescore=True,
    )
