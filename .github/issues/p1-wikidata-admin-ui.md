## Context

When `WikidataProvider` cannot auto-link a person (ambiguous or low-confidence match), it creates a `WikidataCandidateReview` record. This issue implements the Django admin interface that lets operators review candidates and accept the correct one, triggering downstream enrichment.

## Admin list view

```python
@admin.register(WikidataCandidateReview)
class WikidataCandidateReviewAdmin(admin.ModelAdmin):
    list_display = (
        "person_link", "query_name", "candidate_count",
        "status", "accepted_qid", "reviewed_by", "created_at"
    )
    list_filter = ("status",)
    search_fields = ("person__name", "query_name", "accepted_qid")
    readonly_fields = ("id", "person", "query_name", "candidates",
                       "reviewed_by", "reviewed_at", "created_at", "updated_at")
    change_form_template = "admin/persons/wikidatacandidatereview/change_form.html"

    def candidate_count(self, obj):
        return len(obj.candidates or [])
    candidate_count.short_description = "Candidates"

    def person_link(self, obj):
        url = reverse("admin:persons_person_change", args=[obj.person_id])
        return format_html('<a href="{}">{}</a>', url, obj.person)
    person_link.short_description = "Person"
```

## Custom change form template

`src/web/templates/admin/persons/wikidatacandidatereview/change_form.html`

Extends `admin/change_form.html`. Replaces the `candidates` JSONField raw display with a rendered card UI.

### Card layout (per candidate)

Each candidate in `obj.candidates` renders as a card containing:

**Header row:**
- Wikidata label (bold) + description (muted)
- Disambiguation score badge: `score ≥ 0.85` → green, `0.60–0.85` → yellow, `< 0.60` → red
- Radio button: `<input type="radio" name="accepted_qid" value="{qid}">`

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

### Form actions (below cards)

When status is `pending`:
- Accept selected candidate → sets `status="accepted"`, `accepted_qid=<radio value>`, `reviewed_by=request.user`, `reviewed_at=now()`
- Reject (no match) → sets `status="rejected"`
- Skip for now → sets `status="skipped"`

The form submits to a custom `response_change()` override on the admin class (not a separate view).

### CSS

Use standard Django admin CSS variables. No external CSS frameworks. Cards use inline styles or a small `<style>` block in the template for portability.

## Implementation notes

- The template must handle `candidates = []` gracefully (show a "No candidates" message)
- The radio button selection must be validated server-side before saving: if `accepted_qid` is submitted, it must be present in `candidates[*].qid`
- Saving with "Accept" when no radio is selected shows a form error: "Please select a candidate."
- After a successful accept, the admin redirects back to the `WikidataCandidateReview` list filtered to `status=pending`

## Acceptance criteria

- [ ] List view shows pending reviews prominently (default filter: `status=pending`)
- [ ] Change view renders candidate cards (not raw JSON)
- [ ] Score badge color coding correct
- [ ] Facts table populated from `candidates[*].properties`
- [ ] Wikipedia extract shown when available
- [ ] Image shown when available
- [ ] All three action buttons work (accept, reject, skip)
- [ ] Accept validates radio selection server-side
- [ ] Accepted review triggers downstream enrichment (via signal from previous issue)
- [ ] Reviewed_by and reviewed_at set correctly on accept
- [ ] Template tested with zero candidates, one candidate, multiple candidates
- [ ] Manual end-to-end test: create a review via shell, accept via admin, verify EnrichmentRun created
