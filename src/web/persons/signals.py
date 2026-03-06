"""Django signals for the persons app."""

from django.db.models.signals import post_save

from src.core.logging import get_logger

logger = get_logger(__name__)


def _connect_signals() -> None:
    """Import models and connect all signals. Called from PersonsConfig.ready()."""
    # Import here to avoid AppRegistryNotReady errors at module load time.
    from src.web.persons.models import WikidataCandidateReview  # noqa: PLC0415

    post_save.connect(_on_review_resolved, sender=WikidataCandidateReview)


def _on_review_resolved(
    sender,  # noqa: ANN001
    instance,  # noqa: ANN001
    created: bool,
    **kwargs,  # noqa: ANN003
) -> None:
    """
    Dispatch the appropriate action when a review reaches a terminal status.

    Does nothing on create (only reacts to updates).

    accepted  -> run full enrichment with confirmed QID (downstream providers included)
    confirmed -> bump confidence on already-written Wikidata attributes; no re-enrichment
    rejected  -> rollback handled directly in admin response_change() (see #31) because
                 the signal cannot reliably inspect the previous status
    """
    if created:
        return

    from src.core.enrichment.tasks import (  # noqa: PLC0415
        _bump_wikidata_confidence,
        run_enrichment_for_person,
    )

    if instance.status == "accepted" and instance.linked_qid:
        logger.info(
            "WikidataCandidateReview accepted; triggering enrichment",
            extra={
                "person_id": instance.person_id,
                "linked_qid": instance.linked_qid,
                "review_id": str(instance.pk),
            },
        )
        run_enrichment_for_person(
            person_id=instance.person_id,
            triggered_by="adjudication",
            confirmed_wikidata_qid=instance.linked_qid,
        )
    elif instance.status == "confirmed":
        logger.info(
            "WikidataCandidateReview confirmed; bumping Wikidata confidence",
            extra={
                "person_id": instance.person_id,
                "review_id": str(instance.pk),
            },
        )
        _bump_wikidata_confidence(
            person_id=instance.person_id,
            reviewed_by_id=instance.reviewed_by_id,
        )
