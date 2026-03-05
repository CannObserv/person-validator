## Context

Wikidata contains ~10,028 external identifier properties. Of those, **2,394** are applicable to human persons (Q5) via subject-type constraints, and ~1,128 are classified as "authority control for people." Rather than hardcoding an allowlist, we import the full taxonomy into a local model and expose it in Django admin for narrowing.

This model is the reference table that `WikidataProvider` consults at runtime to decide which Wikidata properties to extract and how to construct `platform_url` values from raw identifier strings.

## Domain knowledge: Wikidata property taxonomy

Every Wikidata property item carries `P31` (instance of) statements pointing into a class hierarchy linked by `P279` (subclass of). The most important node for person identity work is:

**`Q19595382`** — "Wikidata property for authority control for people"

Sub-categories of Q19595382 (with approximate property counts):
- `Q55650689` — for writers (~178)
- `Q55653847` — for artists (~144)
- `Q66712599` — for musicians and musical ensembles (~176)
- `Q93433126` — for politicians (~140)
- `Q93436926` — for sports people (~189)
- `Q97584729` — biographical dictionaries (~160)

Additional cross-cutting categories relevant to persons:
- `Q62589316` — identifier suggesting notability (~474)
- `Q105388954` — online account identifier (~73)
- `Q108075891` — open-access repository identifier (~84)

**Key meta-properties:**
- `P1630` — formatter URL: URL template where `$1` is the identifier value, e.g. `https://viaf.org/viaf/$1`
- `P1629` — subject item: the Wikidata item for the database/system the property connects to (e.g. Q54919 = VIAF)
- `P2302` — property constraint (anchor for subject-type constraint statements)
- `P2308` — class (qualifier on P2302 constraint): the item type the property applies to
- `P2309` — relation (qualifier, often omitted): instance-of vs subclass-of

**Subject-type constraint pattern:** A property `P` applies to humans if:
```
P p:P2302 [ ps:P2302 wd:Q21503250 ; pq:P2308 wd:Q5 ]
```
Do **not** filter on `P2309` — most properties omit it even when they mean "instance of."

## Model

Add to `src/web/persons/models.py`:

```python
class ExternalIdentifierProperty(models.Model):
    """
    A Wikidata external identifier property applicable to human persons.

    Populated and refreshed by the `sync_wikidata_properties` management command.
    Used by WikidataProvider to determine which properties to extract and
    how to construct platform_url values via formatter_url.

    The `is_enabled` flag allows administrators to narrow which properties
    WikidataProvider actively extracts. All imported properties are enabled
    by default; disable selectively to suppress noisy or low-value identifiers.

    Namespace note: `slug` here is independent of `ExternalPlatform.slug`.
    When a corresponding ExternalPlatform exists (e.g. slug="viaf"), link it
    via `platform` FK. WikidataProvider uses this FK to associate extracted
    identifier values with the correct ExternalPlatform when creating
    platform_url attributes.
    """

    wikidata_property_id = models.CharField(
        max_length=20, unique=True,
        help_text='Wikidata property ID, e.g. "P214"',
    )
    slug = models.SlugField(
        max_length=100, unique=True,
        help_text="URL-safe identifier derived from English property label.",
    )
    display = models.CharField(max_length=200, help_text="English property label.")
    description = models.TextField(blank=True, help_text="English property description.")
    formatter_url = models.CharField(
        max_length=500, blank=True,
        help_text="P1630 value. Replace $1 with the identifier value to get the URL.",
    )
    subject_item_label = models.CharField(
        max_length=200, blank=True,
        help_text="English label of the P1629 subject item (the database/system).",
    )
    taxonomy_categories = models.JSONField(
        default=list,
        help_text="List of Wikidata QIDs (P31 values) classifying this property.",
    )
    platform = models.ForeignKey(
        "ExternalPlatform",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="identifier_properties",
        help_text="Linked ExternalPlatform, if one exists for this identifier system.",
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text="When False, WikidataProvider skips this property during extraction.",
    )
    sort_order = models.PositiveIntegerField(default=0)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "persons_externalidentifierproperty"
        ordering = ["sort_order", "wikidata_property_id"]
        verbose_name = "External Identifier Property"
        verbose_name_plural = "External Identifier Properties"

    def __str__(self) -> str:
        return f"{self.wikidata_property_id} — {self.display}"

    def build_url(self, identifier_value: str) -> str | None:
        """Return the full URL for the given identifier value, or None if no formatter_url."""
        if not self.formatter_url:
            return None
        return self.formatter_url.replace("$1", identifier_value)
```

## Management command: `sync_wikidata_properties`

Location: `src/web/persons/management/commands/sync_wikidata_properties.py`

### Behaviour

1. Query Wikidata SPARQL for all external-id properties with a Q5 subject-type constraint (paginated, 500 per request).
2. For each result: upsert `ExternalIdentifierProperty` (create or update all fields except `is_enabled`).
3. After upsert: attempt to auto-link to an existing `ExternalPlatform` by matching slug (if `platform` FK is null).
4. If a property disappears from the query results on a subsequent run, **do not delete or disable it** — log a warning instead.
5. Print a summary: created N, updated N, skipped N, warnings N.

### Slug generation

Derive slug from English property label: lowercase, replace spaces with hyphens, strip non-alphanumeric-hyphen characters, collapse consecutive hyphens. If the resulting slug collides with an existing record (different `wikidata_property_id`), append `-{property_id_lowercase}` (e.g. `viaf-cluster-id-p214`).

### SPARQL query (paginated)

```sparql
SELECT DISTINCT
  ?prop ?propLabel ?propDescription ?formatterURL ?subjectItemLabel
  (GROUP_CONCAT(DISTINCT ?catQID; separator="|") AS ?categories)
WHERE {
  ?prop wikibase:propertyType wikibase:ExternalId .
  ?prop p:P2302 [ ps:P2302 wd:Q21503250 ; pq:P2308 wd:Q5 ] .
  OPTIONAL { ?prop wdt:P1630 ?formatterURL . }
  OPTIONAL {
    ?prop wdt:P1629 ?subjectItem .
    ?subjectItem rdfs:label ?subjectItemLabel .
    FILTER(LANG(?subjectItemLabel) = "en")
  }
  OPTIONAL {
    ?prop wdt:P31 ?cat .
    BIND(STR(?cat) AS ?catQID)
  }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
}
GROUP BY ?prop ?propLabel ?propDescription ?formatterURL ?subjectItemLabel
ORDER BY ?prop
LIMIT 500
OFFSET {offset}
```

Endpoint: `https://query.wikidata.org/sparql`  
Method: GET with `query=...&format=json`  
Required header: `User-Agent: PersonValidator/0.1 (greg@cannabis.observer)`  
Retry on HTTP 429/503 with exponential backoff (max 3 retries).

### Auto-link logic

After upserting a property, if `platform` is null:
```python
slug_candidates = [property.slug]
# Also try matching on the property's own wikidata_property_id lowercased
platform = ExternalPlatform.objects.filter(slug__in=slug_candidates, is_active=True).first()
if platform:
    property.platform = platform
    property.save(update_fields=["platform"])
```

## Django admin

```python
@admin.register(ExternalIdentifierProperty)
class ExternalIdentifierPropertyAdmin(admin.ModelAdmin):
    list_display = ("wikidata_property_id", "display", "is_enabled", "platform",
                    "formatter_url", "last_synced_at")
    list_filter = ("is_enabled",)
    search_fields = ("wikidata_property_id", "slug", "display", "description")
    list_editable = ("is_enabled",)  # toggle from list view
    readonly_fields = ("wikidata_property_id", "slug", "last_synced_at")
    raw_id_fields = ("platform",)
```

## Acceptance criteria

- [ ] `ExternalIdentifierProperty` model exists with all fields above
- [ ] `build_url()` method works correctly
- [ ] `sync_wikidata_properties` command runs without error against live Wikidata
- [ ] Command upserts correctly (re-running is idempotent)
- [ ] Slug collision handling works
- [ ] Auto-link to `ExternalPlatform` works for pre-seeded platforms
- [ ] Django admin shows properties with inline `is_enabled` toggle
- [ ] Tests cover: model, `build_url`, slug generation, auto-link logic
- [ ] Live API call is mocked in tests; a separate integration test (marked `@pytest.mark.integration`) hits the real endpoint
