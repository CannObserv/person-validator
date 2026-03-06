"""Django signals for the persons app."""

from django.db.models.signals import post_save, pre_save

from src.core.logging import get_logger
from src.web.persons.review_handlers import DISPATCH

logger = get_logger(__name__)


def _connect_signals() -> None:
    """Connect all persons app signals.  Called from PersonsConfig.ready()."""
    # Import deferred here to guarantee app registry is ready before the model
    # class is resolved (this function is only ever called from ready()).
    from src.web.persons.models import WikidataCandidateReview  # noqa: PLC0415

    pre_save.connect(_on_review_pre_save, sender=WikidataCandidateReview)
    post_save.connect(_on_review_post_save, sender=WikidataCandidateReview)


def _on_review_pre_save(
    sender: type,
    instance: object,
    **kwargs: object,
) -> None:
    """Snapshot the current persisted status onto the instance before saving.

    Stores the value as ``instance._previous_status`` so that the post_save
    handler can detect genuine transitions and avoid re-firing on unrelated
    field updates to an already-terminal review.
    """
    if instance.pk:  # type: ignore[union-attr]
        try:
            previous = (
                sender.objects.values_list("status", flat=True).get(pk=instance.pk)  # type: ignore[union-attr]  # type: ignore[union-attr]
            )
        except sender.DoesNotExist:  # type: ignore[union-attr]
            previous = None
    else:
        previous = None
    instance._previous_status = previous  # type: ignore[union-attr]


def _on_review_post_save(
    sender: type,
    instance: object,
    created: bool,
    **kwargs: object,
) -> None:
    """Dispatch a handler when a review transitions to a new actionable status.

    Does nothing on create or when the status has not changed.  Routing is
    table-driven via ``review_handlers.DISPATCH``.
    """
    if created:
        return

    previous = getattr(instance, "_previous_status", None)
    current = instance.status  # type: ignore[union-attr]

    if previous == current:
        return

    handler = DISPATCH.get(current)
    if handler is not None:
        handler(instance)
