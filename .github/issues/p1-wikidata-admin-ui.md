## Context

When `WikidataProvider` cannot auto-link a person (ambiguous or low-confidence match), it creates a `WikidataCandidateReview` record. This issue implements the Django admin interface that lets operators review candidates and accept the correct one, triggering downstream enrichment.

## Admin list view

```python
@admin.register(WikidataCandidateReview)
class WikidataCandidateReviewAdmin(admin.ModelAdmin):
    list_display = (
        "person_link", "query_name", "review_type", "candidate_count",
        "status", "linked_qid", "reviewed_by", "created_at"
    )
    list_filter = ("status",)
    search_fields = ("person__name", "query_name", "linked_qid")
    readonly_fields = ("id", "person", "query_name", "candidates",
                       "reviewed_by", "reviewed_at", "created_at", "updated_at")
    change_form_template = "admin/persons/wikidatacandidatereview/change_form.html"

    def get_queryset(self, request):
        """Default to showing only actionable (unresolved) reviews."""
        qs = super().get_queryset(request)
        if not request.GET.get("status__in"):
            return qs.filter(status__in=["pending", "auto_linked"])
        return qs

    def candidate_count(self, obj):
        return len(obj.candidates or [])
    candidate_count.short_description = "Candidates"

    def review_type(self, obj):
        """Display a human-readable type badge."""
        if obj.status == "auto_linked":
            return format_html('<span style="color:#1d76db">&#9679; Auto-linked</span>')
        return format_html('<span style="color:#e67e22">&#9679; Ambiguous</span>')
    review_type.short_description = "Type"

    def person_link(self, obj):
        url = reverse("admin:persons_person_change", args=[obj.person_id])
        return format_html('<a href="{}">{}</a>', url, obj.person)
    person_link.short_description = "Person"
```

## Custom change form template

`src/web/templates/admin/persons/wikidatacandidatereview/change_form.html`

Extends `admin/change_form.html`. Replaces the `candidates` JSONField raw display with a rendered card UI. Supports two modes based on `object.status`.

### Card layout (per candidate) — shared between both modes

Each candidate in `obj.candidates` renders as a card containing:

**Header row:**
- Wikidata label (bold) + description (muted)
- Disambiguation score badge: `score ≥ 0.85` → green, `0.60–0.85` → yellow, `< 0.60` → red
- **Mode A (pending) only:** Radio button `<input type="radio" name="linked_qid" value="{qid}">`
- **Mode B (auto_linked) only:** "Currently linked" badge (blue/teal) in place of radio button

**Facts table:**
| Field | Value |
|---|---|
| Wikidata QID | Q23 (linked to `https://www.wikidata.org/wiki/Q23`) |
| Birth date | 1732-02-22 |
| Death date | 1799-12-14 |
| Occupation(s) | politician, military officer |
| Nationality | American |

**Wikipedia section** (shown only if `wikipedia_url` is not null):
- Article URL (external link, opens new tab)
- Extract text (first ~300 chars, italic, collapsible "Read more" link)

**Image** (shown only if `image_url` is not null):
- Thumbnail, right-floated, max 80px wide

**"View full Wikidata entry" link** — always shown, opens new tab.

### Mode A — pending (ambiguous match, choose from candidates)

**Form actions (below cards):**
- Accept selected candidate → sets `status="accepted"`, `linked_qid=<radio value>`, `reviewed_by=request.user`, `reviewed_at=now()`
- Reject (no match) → sets `status="rejected"`
- Skip for now → sets `status="skipped"`

Validation: if Accept is clicked with no radio selected, show form error "Please select a candidate."

### Mode B — auto_linked (unambiguous auto-link, confirm or reject)

The single candidate card shows the auto-linked entity (no radio). Below the card, show:

```
Current confidence: 0.75 → 0.95 after confirmation
```

**Form actions:**
- **Confirm** → sets `status="confirmed"`, `reviewed_by=request.user`, `reviewed_at=now()`; triggers `_bump_wikidata_confidence()` via post-save signal
- **Reject** → sets `status="rejected"`; calls `_rollback_wikidata_autolink()` directly (not via signal); redirects to new pending review once re-queued

No "Skip" action for auto-linked reviews — the link is already active and does not block anything.

### Resolved reviews

For reviews with `status` in `{accepted, confirmed, rejected, skipped}`, the change form is read-only. Show a banner: "This review was resolved on {reviewed_at} by {reviewed_by}." No action buttons.

### CSS

Use standard Django admin CSS variables. No external CSS frameworks. Cards use inline styles or a small `<style>` block in the template for portability.

## Implementation notes

- The template must handle `candidates = []` gracefully (show a "No candidates" message)
- `linked_qid` submission is validated server-side: value must be present in `candidates[*].qid`
- After a successful accept or confirm, redirect back to the `WikidataCandidateReview` changelist filtered to actionable statuses
- After a rejection rollback, redirect to the person's admin change page so the operator can see the new pending review
- See #31 for the full confirmation/rollback utility function specifications

## Acceptance criteria

- [ ] List view default shows `pending` and `auto_linked` reviews (actionable filter)
- [ ] `review_type` column distinguishes Ambiguous vs Auto-linked with colour badges
- [ ] Change view renders candidate cards (not raw JSON) for both modes
- [ ] Score badge colour coding correct
- [ ] Facts table populated from `candidates[*].properties`
- [ ] Wikipedia extract shown when available
- [ ] Image shown when available
- [ ] Mode A (pending): accept/reject/skip buttons work; accept validates radio selection server-side
- [ ] Mode B (auto_linked): confirm/reject buttons work; no radio required
- [ ] Mode B confirm: shows confidence transition (0.75 → 0.95) in UI
- [ ] Mode B reject: calls rollback directly, redirects to person page
- [ ] Resolved reviews render as read-only with resolution banner
- [ ] `linked_qid` used throughout (not `accepted_qid`)
- [ ] Accepted review triggers downstream enrichment (via signal, see #20)
- [ ] Confirmed review triggers confidence bump (via signal, see #20 and #31)
- [ ] `reviewed_by` and `reviewed_at` set correctly on accept and confirm
- [ ] Template tested with zero candidates, one candidate, multiple candidates
- [ ] Manual end-to-end test: create auto_linked review via shell, confirm via admin, verify confidence = 0.95
- [ ] Manual end-to-end test: create auto_linked review, reject via admin, verify rollback and new pending review
