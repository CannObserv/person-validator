## Problem

When `WikidataProvider` finds a single unambiguous candidate above the auto-link threshold, it writes attributes directly with `confidence=0.75` and creates no review record. There is no mechanism for an admin to inspect the auto-link, confirm it is correct, or reject it — and no path to the higher `confidence=0.95` awarded to human-adjudicated matches.

This means auto-linked persons are permanently capped at 0.75 unless a re-enrichment accidentally creates a review.

## Design

`WikidataCandidateReview` already models the relationship between a person and a Wikidata entity. We extend it to cover auto-links by adding two new statuses:

| Status | Meaning | Created by |
|---|---|---|
| `pending` | Ambiguous — admin must select from candidates | WikidataProvider |
| `auto_linked` | Unambiguous auto-link — optionally awaiting admin confirmation | WikidataProvider |
| `accepted` | Admin selected a candidate from a `pending` review | Admin |
| `confirmed` | Admin confirmed an `auto_linked` review | Admin |
| `rejected` | Admin rejected — no valid match | Admin (from either `pending` or `auto_linked`) |
| `skipped` | Deferred — try again later | Admin |

The auto-link path now always produces a `WikidataCandidateReview(status="auto_linked")`. Attributes are still written immediately at `confidence=0.75` — the review is non-blocking. When an admin opens the review and clicks **Confirm**, all Wikidata-sourced attributes and name records for that person are updated to `confidence=0.95`. When an admin clicks **Reject**, the Wikidata-sourced attributes are removed and the person is re-queued for manual search.

### Status transitions (state machine)

```
(WikidataProvider auto-link)
  → auto_linked  --[Confirm]-→  confirmed
                 --[Reject]--→  rejected  → (re-queue: new pending review)

(WikidataProvider ambiguous)
  → pending      --[Accept]--→  accepted
                 --[Reject]--→  rejected
                 --[Skip]----→  skipped   → (stays in queue)
```

Rejected auto-links differ from rejected pending reviews: rejecting an auto-link should delete the already-written Wikidata attributes (they were written without human validation). Rejecting a pending review simply records that no match was found (no attributes were written).

### `WikidataCandidateReview` model changes

**Add two statuses:**
```python
STATUS_CHOICES = [
    ("pending",     "Pending Review"),
    ("auto_linked", "Auto-Linked — Awaiting Confirmation"),  # NEW
    ("accepted",    "Accepted"),
    ("confirmed",   "Confirmed"),                           # NEW
    ("rejected",    "Rejected — No Match"),
    ("skipped",     "Skipped — Review Later"),
]
```

**Change `accepted_qid` semantics:** Rename to `linked_qid`. Populated on:
- `accepted`: the QID the admin selected from candidates
- `confirmed`: the QID that was auto-linked (already populated by WikidataProvider at creation)
- `auto_linked`: same as confirmed — populated at creation time

Rename: `accepted_qid` → `linked_qid` in model, migration, admin, signal, and all references.

**Update `help_text`:**
```python
linked_qid = models.CharField(
    max_length=20, blank=True,
    help_text=(
        "The accepted or auto-linked QID. "
        "Populated at creation for auto_linked reviews; "
        "set by admin action for accepted reviews."
    ),
)
```

### `WikidataProvider` changes

On auto-link path:
```python
# After writing attributes at confidence=0.75:
WikidataCandidateReview.objects.create(
    person=person_obj,
    query_name=person.name,
    candidates=[{...single candidate dict, same schema as pending...}],
    status="auto_linked",
    linked_qid=qid,
)
```

The `candidates` list contains exactly one entry — the auto-linked entity — using the same schema as pending reviews (label, description, score, wikipedia_url, extract, properties). This allows the admin UI to render the same card template for both review types.

### Post-save signal changes (issue #20)

The signal currently fires only on `status="accepted"`. It must also fire on `status="confirmed"`, but with a different handler:

```python
@receiver(post_save, sender=WikidataCandidateReview)
def on_review_resolved(sender, instance, **kwargs):
    if instance.status == "accepted" and instance.linked_qid:
        # Candidate selected from ambiguous set → run full enrichment
        run_enrichment_for_person(
            person_id=instance.person_id,
            triggered_by="adjudication",
            confirmed_wikidata_qid=instance.linked_qid,
        )
    elif instance.status == "confirmed":
        # Auto-link confirmed → update confidence only, no re-enrichment needed
        _bump_wikidata_confidence(
            person_id=instance.person_id,
            reviewed_by_id=instance.reviewed_by_id,
        )
    elif instance.status == "rejected":
        previous_status = kwargs.get("update_fields")  # detect rejection source
        # Only roll back attributes if we're rejecting an auto_linked review
        # (accepted→rejected handled by the admin's response_change logic directly)
```

**Important:** The signal alone cannot reliably detect whether the rejection came from an `auto_linked` or a `pending` state. The admin `response_change()` override should call the rollback logic directly rather than relying on the signal for the rejected-auto-link case.

### `_bump_wikidata_confidence()` utility

In `src/core/enrichment/tasks.py`:

```python
def _bump_wikidata_confidence(person_id: str, reviewed_by_id: int | None) -> None:
    """
    Raise confidence on all Wikidata-sourced PersonAttribute and PersonName
    records for this person from AUTO_LINK_CONFIDENCE to CONFIRMED_CONFIDENCE.

    Only updates records currently at AUTO_LINK_CONFIDENCE (0.75) to avoid
    overwriting records that were re-enriched by other means at a different score.
    Also updates PersonName.confidence from ALIAS_CONFIDENCE (0.70) to
    CONFIRMED_ALIAS_CONFIDENCE (0.80).
    """
    from src.web.persons.models import PersonAttribute, PersonName

    PersonAttribute.objects.filter(
        person_id=person_id,
        source="wikidata",
        confidence=WikidataProvider.AUTO_LINK_CONFIDENCE,
    ).update(confidence=WikidataProvider.CONFIRMED_CONFIDENCE, updated_at=timezone.now())

    PersonName.objects.filter(
        person_id=person_id,
        source="wikidata",
        confidence=WikidataProvider.ALIAS_CONFIDENCE,
    ).update(confidence=WikidataProvider.CONFIRMED_ALIAS_CONFIDENCE, updated_at=timezone.now())
```

**Confidence constants on `WikidataProvider`:**

```python
AUTO_LINK_CONFIDENCE    = 0.75   # written on auto-link
CONFIRMED_CONFIDENCE    = 0.95   # written on confirmed QID mode; bumped to on confirmation
ALIAS_CONFIDENCE        = 0.70   # PersonName aliases from auto-link
CONFIRMED_ALIAS_CONFIDENCE = 0.80  # PersonName aliases after confirmation
```

### Rollback utility (rejected auto-link)

```python
def _rollback_wikidata_autolink(person_id: str) -> None:
    """
    Delete all Wikidata-sourced PersonAttribute and PersonName records
    for this person that were written at AUTO_LINK_CONFIDENCE (0.75).

    Called when an admin rejects an auto_linked review.
    Re-queues the person for manual Wikidata search by creating a new
    pending WikidataCandidateReview via a fresh WikidataProvider.enrich() call.
    """
    PersonAttribute.objects.filter(
        person_id=person_id,
        source="wikidata",
        confidence=WikidataProvider.AUTO_LINK_CONFIDENCE,
    ).delete()

    PersonName.objects.filter(
        person_id=person_id,
        source="wikidata",
        confidence=WikidataProvider.ALIAS_CONFIDENCE,
    ).delete()

    # Re-trigger search without confirmed_qid → will create a new pending review
    run_enrichment_for_person(
        person_id=person_id,
        triggered_by="adjudication",
        provider_names=["wikidata"],
        force_rescore=True,  # ignore existing wikidata_qid attribute
    )
```

`force_rescore=True` instructs `WikidataProvider.enrich()` to ignore any existing `wikidata_qid` attribute and perform a fresh search. This avoids immediately re-linking to the just-rejected QID.

### Admin UI changes (issue #22)

The change form template must handle two review modes:

**Mode A — pending** (existing behaviour, unchanged):
- Card per candidate with radio buttons
- Actions: Accept (requires radio selection), Reject, Skip

**Mode B — auto_linked** (new):
- Single card showing the auto-linked entity (no radio button — it's already linked)
- Card header includes a **"Currently linked"** badge (blue/teal)
- Confidence indicator: "Current confidence: 0.75 → 0.95 after confirmation"
- Actions: **Confirm** (bumps confidence), **Reject** (rolls back and re-queues)
- No "Skip" action (auto-links don't need deferral — they're already active)

**List view additions:**
- `auto_linked` status badge styled distinctly from `pending` (e.g. blue vs yellow)
- Default filter: `status__in=["pending", "auto_linked"]` — both actionable states visible together
- Add column `review_type` showing "Ambiguous" or "Auto-linked" derived from status

## Updated `accepted_qid` → `linked_qid` migration

```python
migrations.RenameField(
    model_name="wikidatacandidatereview",
    old_name="accepted_qid",
    new_name="linked_qid",
)
```

## Updated confidence convention

| Link method | Confidence |
|---|---|
| Auto-linked, unconfirmed (`auto_linked` review) | 0.75 |
| Auto-linked, admin confirmed (`confirmed` review) | 0.95 |
| Admin-adjudicated from candidates (`accepted` review) | 0.95 |
| Derived from confirmed Wikidata identifier | 0.90 |
| Downstream provider data | 0.85 |
| Name alias — auto-linked, unconfirmed | 0.70 |
| Name alias — confirmed | 0.80 |

## Issues affected

- **#20** — `WikidataCandidateReview` model: add statuses, rename `accepted_qid` → `linked_qid`
- **#21** — `WikidataProvider`: create `auto_linked` review on auto-link path; add confidence constants; `force_rescore` parameter
- **#22** — Admin UI: Mode B (auto_linked) template, confirm/reject actions, list view updates
- **#29** — Epic: update confidence convention table

## Acceptance criteria

- [ ] `auto_linked` and `confirmed` statuses added to `WikidataCandidateReview`
- [ ] `accepted_qid` renamed to `linked_qid` (migration + all references)
- [ ] `WikidataProvider` creates `WikidataCandidateReview(status="auto_linked")` on every auto-link
- [ ] `_bump_wikidata_confidence()` updates `PersonAttribute` and `PersonName` confidence correctly
- [ ] Only records at exactly `AUTO_LINK_CONFIDENCE` (0.75) / `ALIAS_CONFIDENCE` (0.70) are updated
- [ ] `_rollback_wikidata_autolink()` deletes auto-linked attributes and re-queues search
- [ ] `force_rescore=True` prevents immediate re-linking to the rejected QID
- [ ] Post-save signal handles `confirmed` status (calls `_bump_wikidata_confidence`)
- [ ] Admin change form: Mode B renders correctly for `auto_linked` reviews
- [ ] Mode B "Confirm" action bumps confidence and sets `status="confirmed"`, `reviewed_by`, `reviewed_at`
- [ ] Mode B "Reject" action calls rollback and sets `status="rejected"`
- [ ] List view default filter includes both `pending` and `auto_linked`
- [ ] List view `review_type` column distinguishes the two modes
- [ ] Confirmation of an already-confirmed review is idempotent (no double-bump)
- [ ] Tests: bump utility, rollback utility, signal dispatch, admin action paths
- [ ] Manual end-to-end test: auto-link a person, confirm via admin, verify confidence = 0.95
- [ ] Manual end-to-end test: auto-link a person, reject via admin, verify attributes deleted, new pending review created
