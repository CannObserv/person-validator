# Enrichment Provider System — Design Document

> Status: Pre-implementation design. Supersedes ad-hoc provider notes.
> Decisions recorded here reflect the full interview session with the project owner.

---

## Table of Contents

1. [Model Changes](#1-model-changes)
2. [Provider Dependency Mechanism](#2-provider-dependency-mechanism)
3. [Enrichment Run History](#3-enrichment-run-history)
4. [Wikidata External Identifier Taxonomy](#4-wikidata-external-identifier-taxonomy)
5. [WikidataCandidateReview — Adjudication](#5-wikidatacandidatereview--adjudication)
6. [Provider Catalogue](#6-provider-catalogue)
7. [Change Subscription Strategy](#7-change-subscription-strategy)
8. [Confidence Scoring Convention](#8-confidence-scoring-convention)
9. [Implementation Phases](#9-implementation-phases)
10. [Open Questions](#10-open-questions)

---

## 1. Model Changes

### 1.1 `SocialPlatform` → `ExternalPlatform`

`SocialPlatform` is renamed `ExternalPlatform` throughout. Rationale: platform_url
attributes cover authoritative identity systems (Wikidata, VIAF, ORCID) that are
not "social" in any sense. The rename covers:

- Model class: `SocialPlatform` → `ExternalPlatform`
- DB table: `persons_socialplatform` → `persons_externalplatform`
- Admin registration and all imports

A data migration renames the table. The `WikidataProvider` (and future providers)
may call `ExternalPlatform.objects.get_or_create(slug=..., defaults={...})` to
register new platforms on the fly.

**Default platforms to seed (additions beyond the existing social set):**

| slug | display | sort_order |
|---|---|---|
| `wikidata` | Wikidata | 100 |
| `wikipedia` | Wikipedia | 101 |
| `viaf` | VIAF | 110 |
| `isni` | ISNI | 111 |
| `loc` | Library of Congress | 112 |
| `gnd` | GND | 113 |
| `orcid` | ORCID | 120 |
| `imdb` | IMDb | 130 |
| `musicbrainz` | MusicBrainz | 131 |
| `ballotpedia` | Ballotpedia | 140 |
| `opensecrets` | OpenSecrets | 141 |

### 1.2 `PersonName` — Add `confidence` and `provenance`

`PersonName` currently has `source` (CharField) but no structured provenance
or confidence. Two fields are added:

```python
confidence = models.FloatField(
    validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    null=True, blank=True,
    help_text="Certainty score [0,1] for this name record. Null = unscored."
)
provenance = models.JSONField(
    null=True, blank=True,
    help_text=(
        "Structured provenance metadata. Schema is source-dependent. "
        "Common keys: provider, retrieved_at, source_url, wikidata_qid, "
        "wikidata_alias_lang."
    )
)
```

When `WikidataProvider` creates `PersonName` aliases, it populates:

```json
{
    "provider": "wikidata",
    "retrieved_at": "2025-07-10T14:00:00Z",
    "wikidata_qid": "Q23",
    "wikidata_alias_lang": "en",
    "source_url": "https://www.wikidata.org/wiki/Q23"
}
```

**Name type inference from Wikidata aliases:** Use `alias` by default. The
following heuristics may upgrade the type:
- Alias matches a `given_name` pattern and differs only in the given name field
  → consider `nickname`
- Alias is in non-Latin script → `transliteration`
- Alias is all-caps or abbreviated (≤6 chars) → `abbreviation`
These heuristics should be documented in the provider and kept conservative.

### 1.3 `ExternalIdentifierProperty` — New Model

Stores the Wikidata external identifier property taxonomy, imported via a
management command and refreshed weekly. Drives `WikidataProvider` extraction
and admin narrowing.

```python
class ExternalIdentifierProperty(models.Model):
    wikidata_property_id = models.CharField(max_length=20, unique=True)  # e.g. "P214"
    slug = models.SlugField(max_length=100, unique=True)                 # e.g. "viaf"
    display = models.CharField(max_length=200)                           # e.g. "VIAF cluster ID"
    description = models.TextField(blank=True)
    formatter_url = models.CharField(max_length=500, blank=True)         # P1630 value
    subject_item_label = models.CharField(max_length=200, blank=True)    # P1629 label
    taxonomy_categories = models.JSONField(default=list)                 # list of category QIDs
    is_enabled = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "persons_externalidentifierproperty"
        ordering = ["sort_order", "wikidata_property_id"]
```

**Management command:** `manage.py sync_wikidata_properties`
- Queries the Wikidata SPARQL endpoint for all external-id properties with a Q5
  (human) subject-type constraint (returns ~2,394 properties).
- Upserts `ExternalIdentifierProperty` records; does not disable existing records
  that disappear from the query (log a warning instead).
- Scheduled weekly via Django management command invoked by cron.

**SPARQL query used (authoritative):**

```sparql
SELECT DISTINCT
  ?prop ?propLabel ?propDescription ?formatterURL ?subjectItemLabel
  (GROUP_CONCAT(DISTINCT ?catLabel; separator="|") AS ?categories)
WHERE {
  ?prop wikibase:propertyType wikibase:ExternalId .
  ?prop p:P2302 [ ps:P2302 wd:Q21503250 ; pq:P2308 wd:Q5 ] .
  OPTIONAL { ?prop wdt:P1630 ?formatterURL . }
  OPTIONAL {
    ?prop wdt:P1629/rdfs:label ?subjectItemLabel .
    FILTER(LANG(?subjectItemLabel) = "en")
  }
  OPTIONAL {
    ?prop wdt:P31 ?cat .
    ?cat rdfs:label ?catLabel .
    FILTER(LANG(?catLabel) = "en")
  }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
}
GROUP BY ?prop ?propLabel ?propDescription ?formatterURL ?subjectItemLabel
ORDER BY ?propLabel
```

Paginate with `LIMIT 500 OFFSET N`. The SPARQL endpoint at
`query.wikidata.org/sparql` requires `User-Agent: PersonValidator/0.1
(greg@cannabis.observer)`.

**Taxonomy QIDs for reference (stored in `taxonomy_categories` JSON):**

| QID | Meaning |
|---|---|
| Q19595382 | Authority control for people (primary filter) |
| Q55650689 | For writers |
| Q55653847 | For artists |
| Q66712599 | For musicians |
| Q93433126 | For politicians |
| Q93436926 | For sports people |
| Q97584729 | Biographical dictionaries |
| Q62589316 | Suggests notability |
| Q105388954 | Online accounts / social |
| Q108075891 | Open-access repositories |

---

## 2. Provider Dependency Mechanism

### 2.1 `Dependency` Dataclass

```python
@dataclass
class Dependency:
    attribute_key: str
    """Attribute key that must be present in existing person attributes."""

    skip_if_absent: bool = True
    """
    If True (default): skip this provider if the dependency attribute is missing.
    If False: run anyway; provider must handle absence gracefully.
    """
```

### 2.2 Updated `Provider` ABC

```python
class Provider(ABC):
    name: str
    dependencies: list[Dependency] = []

    def can_run(self, existing_attribute_keys: set[str]) -> bool:
        """Return True if all skip_if_absent dependencies are satisfied."""
        return all(
            dep.attribute_key in existing_attribute_keys
            for dep in self.dependencies
            if dep.skip_if_absent
        )
```

### 2.3 Topological Execution in `EnrichmentRunner`

The runner resolves dependencies into execution rounds before running:

1. Build a directed graph: edge A→B means "A must run before B" (B depends on A's output key).
2. Topological sort into rounds (BFS by zero-in-degree sets).
3. Providers in the same round have no inter-dependencies → run in parallel
   via `concurrent.futures.ThreadPoolExecutor`.
4. After each round, persist all attributes, refresh `existing_attribute_keys`,
   then dispatch the next round.
5. Raise `CircularDependencyError` if a cycle is detected at startup.

**Concrete execution for our initial provider set:**

```
Round 1 (parallel): WikidataProvider       — no deps
Round 2 (parallel): WikipediaProvider      — dep: wikidata_qid (skip_if_absent=True)
                    VIAFProvider            — dep: wikidata_qid (skip_if_absent=True)
                    ORCIDProvider           — dep: wikidata_qid (skip_if_absent=True)
                    BallotpediaProvider     — dep: wikidata_qid (skip_if_absent=True)
                    OpenSecretsProvider     — dep: wikidata_qid (skip_if_absent=True)
```

All Round 2 providers run in parallel once WikidataProvider has persisted a
`wikidata_qid` attribute. If WikidataProvider produces no output (no match or
ambiguous), all Round 2 providers are skipped per `skip_if_absent=True`.

### 2.4 `PersonData` — Extended

`PersonData` gains `existing_attributes` to pass to providers for disambiguation:

```python
@dataclass
class PersonData:
    id: str
    name: str
    given_name: str | None = None
    middle_name: str | None = None
    surname: str | None = None
    existing_attributes: list[dict] = field(default_factory=list)
    # Each dict: {"key": str, "value": str, "value_type": str, "source": str}
```

The runner populates `existing_attributes` from the DB before running providers.

---

## 3. Enrichment Run History

### 3.1 `EnrichmentRun` Model

```python
class EnrichmentRun(models.Model):
    STATUS_CHOICES = [
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),     # dependency unmet
        ("no_match", "No Match"),   # provider ran, found nothing
    ]

    id = ULIDField(primary_key=True)
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="enrichment_runs")
    provider = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    attributes_saved = models.PositiveIntegerField(default=0)
    attributes_skipped = models.PositiveIntegerField(default=0)
    warnings = models.JSONField(default=list)
    error = models.TextField(blank=True)
    triggered_by = models.CharField(
        max_length=50, blank=True,
        help_text="'cron', 'adjudication', 'manual', 'api'"
    )
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "persons_enrichmentrun"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["person", "provider", "-started_at"]),
        ]
```

### 3.2 Cron Re-enrichment Logic

Hourly cron job: `manage.py run_enrichment_cron`

For each person, for each provider: check `EnrichmentRun.objects.filter(person=p,
provider=name, status__in=["completed","no_match"]).order_by("-started_at").first()`.
If none exists, or if `started_at < now - provider.refresh_interval`, enqueue.

Each provider declares:

```python
class WikidataProvider(Provider):
    name = "wikidata"
    refresh_interval = timedelta(days=7)
```

---

## 4. Wikidata External Identifier Taxonomy

### Key Finding

Wikidata contains **10,028** external-id properties. **2,394** apply specifically
to humans (Q5) via subject-type constraints. Of those, **1,128** are classified as
"authority control for people" (Q19595382). The Wikipedia Authority Control
template maintains a curated subset of **143**.

The SPARQL constraint query (Section 1.3) is the authoritative, always-current
source. Import all 2,394 into `ExternalIdentifierProperty`; admins narrow via
`is_enabled`.

### Formatter URL Pattern

Each external-id property with a web presence carries `P1630` (formatter URL),
e.g. `https://viaf.org/viaf/$1`. `WikidataProvider` constructs `platform_url`
attribute values by substituting the identifier value for `$1`.

### ExternalPlatform Auto-creation

When `WikidataProvider` encounters an identifier whose `ExternalIdentifierProperty`
has a `formatter_url`, it calls:

```python
platform, _ = ExternalPlatform.objects.get_or_create(
    slug=ext_prop.slug,
    defaults={
        "display": ext_prop.display,
        "sort_order": 500,  # provider-created platforms sort after hand-curated
        "is_active": True,
    }
)
```

---

## 5. WikidataCandidateReview — Adjudication

### 5.1 Model

```python
class WikidataCandidateReview(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),   # admin confirms no match
        ("skipped", "Skipped"),     # deferred, try again later
    ]

    id = ULIDField(primary_key=True)
    person = models.ForeignKey(Person, on_delete=models.CASCADE,
                               related_name="wikidata_reviews")
    query_name = models.CharField(max_length=500)
    candidates = models.JSONField()
    # Schema:
    # [
    #   {
    #     "qid": "Q23",
    #     "label": "George Washington",
    #     "description": "1st president of the United States",
    #     "score": 0.87,
    #     "wikipedia_url": "https://en.wikipedia.org/wiki/George_Washington",
    #     "extract": "George Washington was an American Founding Father...",
    #     "properties": {
    #       "birth_date": "1732-02-22",
    #       "death_date": "1799-12-14",
    #       "occupation": ["politician", "military officer"],
    #       "nationality": "United States of America"
    #     }
    #   }
    # ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    accepted_qid = models.CharField(max_length=20, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "persons_wikidatacandidatereview"
        ordering = ["-created_at"]
```

### 5.2 Disambiguation Scoring

`WikidataProvider` scores each candidate against the person's known attributes:

| Signal | Weight | Notes |
|---|---|---|
| Birth year match (±1) | 0.35 | From P569 vs existing `date` attributes |
| Occupation keyword overlap | 0.25 | P106 labels vs existing `text` attributes |
| Nationality/citizenship match | 0.20 | P27 vs existing `location` attributes |
| Name alias match | 0.15 | Wikidata aliases vs PersonName variants |
| Wikipedia article exists | 0.05 | Presence of enwiki sitelink |

**Decision rules:**
- `score ≥ 0.85` AND only one candidate above threshold → auto-link (confidence = 0.75)
- `score ≥ 0.85` AND multiple candidates above threshold → create `WikidataCandidateReview`
- `score < 0.85` for all candidates → create `WikidataCandidateReview` with top-5 candidates
- Zero candidates → `EnrichmentRun` status = `no_match`; no review created

**Confidence values by link method:**
- Auto-linked: `0.75`
- Human-adjudicated (admin accepted): `0.95`

### 5.3 Django Admin Adjudication UI

Custom change form template renders each candidate as a card:
- Wikidata label + description
- Key facts table: birth/death dates, occupation(s), nationality
- Wikipedia extract (first 300 chars) if available
- "View full Wikidata entry" external link (opens in new tab)
- "View Wikipedia article" external link if available
- Radio button to select this candidate

On save with a selected candidate:
1. `accepted_qid` and `reviewed_by` / `reviewed_at` set
2. Post-save signal fires `WikidataProvider.enrich_confirmed(person, qid)`
3. `EnrichmentRunner` is invoked for all downstream providers immediately
   (triggered_by = "adjudication")

Rejected reviews mark the person as "manually reviewed, no match" — the cron
will not re-attempt Wikidata enrichment until the review record is deleted.

---

## 6. Provider Catalogue

### Priority Order (as decided)

1. **Ballotpedia** — US elected officials; MediaWiki API; P2390 = page slug
2. **OpenSecrets** — US campaign finance; REST API (requires key); P4386 = CRP ID
3. **VIAF** — International library authority; REST JSON; P214 = VIAF ID
4. **ORCID** — Academic researcher identity; public REST API; P496 = ORCID iD

All four depend on `wikidata_qid` being present (Round 2 providers).

### Future Providers (researched, not yet scheduled)

| Provider | Wikidata Prop | API Type | Notes |
|---|---|---|---|
| Wikipedia | P18 sitelink | REST (Wikimedia) | Requires wikidata_qid |
| ISNI | P213 | REST JSON | Free, no auth |
| Library of Congress | P244 | REST JSON (id.loc.gov) | Free, no auth |
| GND | P227 | REST JSON (lobid.org) | Free; SPARQL federation works |
| IMDb | P345 | SPARQL federation (QLever) | No scraping needed |
| MusicBrainz | P434 | REST JSON | Free, no auth |
| Semantic Scholar | P7924 | REST API | Free, no auth |
| SNAC | P3430 | REST API | Free |

### SPARQL Federation Capability (confirmed by research)

Two federation patterns were verified with live queries:

**Wikidata → GND (lobid.org):**
```sparql
SELECT ?person ?gndId ?name WHERE {
  ?person wdt:P227 ?gndId .
  SERVICE <https://lobid.org/gnd/search> {
    ... join on gndId ...
  }
}
```

**Wikidata → IMDb (QLever at qlever.dev/api/imdb):**
```sparql
SELECT ?person ?imdbId ?birthYear WHERE {
  ?person wdt:P345 ?imdbId .
  SERVICE <https://qlever.dev/api/imdb> {
    ... join on imdbId ...
  }
}
```

These enable future single-query providers that retrieve Wikidata + external
source data in one round trip.

---

## 7. Change Subscription Strategy

### Mechanism

**Phase 1 (now): Hourly cron polling `recentchange`.**

Management command `run_enrichment_cron` runs hourly. For each provider, the
command checks `EnrichmentRun` records against each provider's `refresh_interval`
and re-enriches stale persons. For Wikidata and Wikipedia, re-enrichment pulls
fresh data from the API; staleness is determined by `refresh_interval` (default
7 days per provider).

**Phase 2 (future): EventStream filtering.**

`stream.wikimedia.org/v2/stream/recentchange` publishes SSE events for every
wiki edit. A future background worker tails this stream, filters for
Wikidata QIDs and Wikipedia titles stored in our attributes, and marks
matching persons as `enrichment_stale = True` for priority re-enrichment.
This is a Kafka-compatible SSE stream — a persistent `systemd` service is
the correct deployment model.

Phase 2 is deferred until there is a meaningful corpus of linked persons.

---

## 8. Confidence Scoring Convention

| Method | Confidence |
|---|---|
| Auto-linked (unambiguous Wikidata match) | 0.75 |
| Human-adjudicated (admin accepted) | 0.95 |
| Derived from confirmed QID (e.g. VIAF ID from Wikidata P214) | 0.90 |
| Downstream provider (e.g. VIAF data, given confirmed VIAF ID) | 0.85 |
| Name alias from Wikidata | 0.70 |

---

## 9. Implementation Phases

### Phase 0: Foundation (prerequisite for all providers)

1. Rename `SocialPlatform` → `ExternalPlatform` (migration + code)
2. Add `confidence` + `provenance` to `PersonName` (migration)
3. Create `ExternalIdentifierProperty` model + management command (migration + command)
4. Create `EnrichmentRun` model (migration)
5. Redesign `EnrichmentRunner`: dependency graph, topological sort, parallel rounds
6. Update `Provider` ABC: `dependencies`, `can_run`, `refresh_interval`
7. Update `PersonData`: `existing_attributes`
8. Seed new `ExternalPlatform` defaults (migration)

### Phase 1: WikidataProvider

1. `WikidataCandidateReview` model (migration)
2. `WikidataProvider` implementation (search, score, link, alias extraction)
3. Django admin adjudication UI (custom change form)
4. Post-save signal → downstream trigger
5. `sync_wikidata_properties` management command
6. Tests (red/green throughout)

### Phase 2: WikipediaProvider

1. `WikipediaProvider` implementation (reads `wikidata_qid` attr, fetches summary)
2. Tests

### Phase 3: VIAF, ORCID, Ballotpedia, OpenSecrets

One provider per iteration, in priority order, each following red/green TDD.

### Phase 4: Cron Infrastructure

1. `run_enrichment_cron` management command
2. Systemd timer unit (weekly `sync_wikidata_properties`, hourly enrichment)

---

## 10. Open Questions

None currently blocking Phase 0. The following will be addressed when relevant:

- **Ballotpedia API depth**: MediaWiki Action API at ballotpedia.org returns
  wikitext; parsing structured person data may require additional heuristics.
  Assess during Phase 3.

- **OpenSecrets API key management**: Key will live in `env` alongside
  `GITHUB_TOKEN`. No change to secrets management strategy needed.

- **IMDb QLever availability**: `qlever.dev` is a research deployment; SLA
  unknown. Treat as best-effort; fall back gracefully.

- **`ExternalIdentifierProperty` slug generation**: Slugs are derived from the
  English property label (lowercased, spaces → hyphens). Collisions are handled
  by appending the property ID (e.g. `viaf-P214`). The slug of a pre-seeded
  `ExternalPlatform` (e.g. `viaf`) should match the auto-generated
  `ExternalIdentifierProperty` slug — seeded slugs are authoritative and the
  sync command should respect them.
