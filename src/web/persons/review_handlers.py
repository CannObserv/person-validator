"""Handlers for WikidataCandidateReview status transitions.

Each handler corresponds to one terminal status value.  ``DISPATCH`` maps
status strings to handler callables; ``signals.py`` uses it to route
``post_save`` events without inline branching or deferred imports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.enrichment.tasks import bump_wikidata_confidence, run_enrichment_for_person
from src.core.logging import get_logger

if TYPE_CHECKING:
    from src.web.persons.models import WikidataCandidateReview

logger = get_logger(__name__)


def handle_accepted(instance: WikidataCandidateReview) -> None:
    """Trigger full enrichment when a review is accepted with a confirmed QID.

    Does nothing if ``linked_qid`` is blank (guard against incomplete saves).
    """
    if not instance.linked_qid:
        logger.warning(
            "WikidataCandidateReview accepted but linked_qid is blank; skipping enrichment",
            extra={"review_id": str(instance.pk), "person_id": instance.person_id},
        )
        return

    logger.info(
        "WikidataCandidateReview accepted; triggering enrichment",
        extra={
            "review_id": str(instance.pk),
            "person_id": instance.person_id,
            "linked_qid": instance.linked_qid,
        },
    )
    run_enrichment_for_person(
        person_id=instance.person_id,
        triggered_by="adjudication",
        confirmed_wikidata_qid=instance.linked_qid,
    )


def handle_confirmed(instance: WikidataCandidateReview) -> None:
    """Bump confidence on existing Wikidata attributes when a review is confirmed."""
    logger.info(
        "WikidataCandidateReview confirmed; bumping Wikidata confidence",
        extra={"review_id": str(instance.pk), "person_id": instance.person_id},
    )
    bump_wikidata_confidence(
        person_id=instance.person_id,
        reviewed_by_id=instance.reviewed_by_id,
    )


# Maps terminal status values to their handler.  Add entries here as new
# statuses gain side-effect behaviour (e.g. a future "escalated" status).
DISPATCH: dict[str, callable] = {
    "accepted": handle_accepted,
    "confirmed": handle_confirmed,
}
