## Context

When `WikidataProvider` searches for a person and finds multiple plausible matches (or one low-confidence match), it must not write any attributes. Instead it creates a `WikidataCandidateReview` record surfacing the candidates for human adjudication in the Django admin. Once an admin selects the correct QID, the provider re-runs in confirmed mode and full downstream enrichment is triggered immediately.

## Model

Add to `src/web/persons/models.py`:

```python
class WikidataCandidateReview(models.Model):
    """
    Holds ambiguous or low-confidence Wikidata search results for human review.

    Created by WikidataProvider when:
    - Multiple candidates score above threshold (ambiguous match)
    - All candidates score below auto-link threshold (uncertain match)

    NOT created when:
    - Zero candidates returned (status no_match recorded on EnrichmentRun)
    - Single candidate scores above auto-link threshold (auto-linked)

    After an admin accepts a candidate, a post-save signal triggers
    WikidataProvider with the confirmed QID and then runs all downstream
    providers (WikipediaProvider, VIAFProvider, etc.) immediately.
    """

    STATUS_CHOICES = [
        ("pending",     "Pending Review"),
        ("auto_linked", "Auto-Linked — Awaiting Confirmation"),  # created on unambiguous auto-link
        ("accepted",   "Accepted"),                              # admin selected from candidates
        ("confirmed",  "Confirmed"),                            # admin confirmed an auto-link
        ("rejected",   "Rejected — No Match"),
        ("skipped",    "Skipped — Review Later"),
    ]

    id = ULIDField(primary_key=True)
    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="wikidata_reviews"
    )
    query_name = models.CharField(
        max_length=500,
        help_text="The name string passed to wbsearchentities.",
    )
    candidates = models.JSONField(
        help_text="""
List of candidate dicts, each with:
  qid (str): Wikidata entity ID, e.g. "Q23"
  label (str): English label
  description (str): English description (Wikidata short description)
  score (float): Disambiguation score [0,1] computed by WikidataProvider
  wikipedia_url (str|null): English Wikipedia article URL, if sitelink exists
  extract (str|null): First ~300 chars of Wikipedia article, if available
  properties (dict): Key biographical facts extracted from the entity:
    birth_date (str|null): ISO 8601 date
    death_date (str|null): ISO 8601 date
    occupations (list[str]): English labels of P106 values
    nationality (str|null): English label of P27 value
    image_url (str|null): Wikimedia Commons thumbnail URL
        """,
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending"
    )
    linked_qid = models.CharField(
        max_length=20, blank=True,
        help_text=(
            "The accepted or auto-linked QID. "
            "Populated at creation time for auto_linked reviews; "
            "set by admin action for accepted reviews."
        ),
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="wikidata_reviews"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "persons_wikidatacandidatereview"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["person", "status"]),
        ]

    def __str__(self) -> str:
        return f"Review for {self.person} ({self.status})"
```

## Post-save signal

In `src/web/persons/signals.py` (create if not exists):

```python
@receiver(post_save, sender=WikidataCandidateReview)
def on_review_resolved(sender, instance, **kwargs):
    """
    Dispatch the appropriate action when a review reaches a terminal status.

    accepted  → run full enrichment with confirmed QID (downstream providers included)
    confirmed → bump confidence on already-written Wikidata attributes; no re-enrichment
    rejected  → if the review was auto_linked, rollback is handled directly in the admin
                response_change() to avoid relying on pre-save state here
    """
    from src.core.enrichment.tasks import run_enrichment_for_person, _bump_wikidata_confidence

    if instance.status == "accepted" and instance.linked_qid:
        run_enrichment_for_person(
            person_id=instance.person_id,
            triggered_by="adjudication",
            confirmed_wikidata_qid=instance.linked_qid,
        )
    elif instance.status == "confirmed":
        _bump_wikidata_confidence(
            person_id=instance.person_id,
            reviewed_by_id=instance.reviewed_by_id,
        )
```

Rejection of an `auto_linked` review triggers `_rollback_wikidata_autolink()` directly inside
the admin `response_change()` method (see #31) rather than via signal, because the signal
cannot reliably inspect the *previous* status.

`run_enrichment_for_person` is a function (not a Celery task — synchronous for now) in `src/core/enrichment/tasks.py` that builds a `PersonData`, runs the full `EnrichmentRunner` with all enabled providers, and handles exceptions.

## Acceptance criteria

- [ ] `WikidataCandidateReview` model exists with all fields above
- [ ] `auto_linked` and `confirmed` statuses present in `STATUS_CHOICES`
- [ ] `accepted_qid` renamed to `linked_qid` (with migration)
- [ ] Both DB indexes present
- [ ] Post-save signal dispatches correctly for `accepted` (re-enrichment) and `confirmed` (confidence bump)
- [ ] Signal is connected in `persons` AppConfig.ready()`
- [ ] `run_enrichment_for_person` and `_bump_wikidata_confidence` utility functions exist and are tested
- [ ] Signal does not fire on create (only on update)
- [ ] Migration applies cleanly
- [ ] Tests cover: signal fires on accept, fires on confirm, does not fire on other status changes
- [ ] See also #31 for full confirmation/rollback behaviour and admin UI requirements
