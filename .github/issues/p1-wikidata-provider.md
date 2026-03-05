## Context

`WikidataProvider` is the foundational enrichment provider. It takes a person record, searches Wikidata for matching human entities, scores candidates against existing person attributes to disambiguate, and either auto-links the person to a Wikidata entity or creates a `WikidataCandidateReview` for human adjudication.

All downstream providers (`WikipediaProvider`, `VIAFProvider`, `ORCIDProvider`, `BallotpediaProvider`, `OpenSecretsProvider`) depend on the `wikidata_qid` attribute this provider writes.

## Domain knowledge: Wikidata APIs

### Search — `wbsearchentities`

```
GET https://www.wikidata.org/w/api.php
  ?action=wbsearchentities
  &search={name}
  &language=en
  &type=item
  &limit=10
  &format=json
```

Returns a list of candidates with `id` (QID), `label`, `description`, `match`. Does **not** filter by entity type — must fetch each candidate to confirm `P31=Q5` (human). Alternative: use SPARQL for combined search + type filter (slower but more precise).

### Entity fetch — `wbgetentities`

```
GET https://www.wikidata.org/w/api.php
  ?action=wbgetentities
  &ids=Q23|Q42|Q937
  &props=labels|descriptions|aliases|claims|sitelinks
  &languages=en
  &format=json
```

Returns full entity JSON. `claims` contains the property values. Batch up to 50 QIDs per request.

### Entity JSON structure (abbreviated)

```json
{
  "entities": {
    "Q23": {
      "id": "Q23",
      "labels": {"en": {"value": "George Washington"}},
      "descriptions": {"en": {"value": "1st president of the United States"}},
      "aliases": {"en": [{"value": "G. Washington"}, ...]},
      "claims": {
        "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}],
        "P569": [{"mainsnak": {"datavalue": {"value": {"time": "+1732-02-22T00:00:00Z"}}}}],
        "P570": [...],
        "P106": [{"mainsnak": {"datavalue": {"value": {"id": "Q82955"}}}}],
        "P27":  [{"mainsnak": {"datavalue": {"value": {"id": "Q30"}}}}],
        "P214": [{"mainsnak": {"datavalue": {"value": "31996712"}}}],
        ...
      },
      "sitelinks": {
        "enwiki": {"title": "George_Washington"}
      }
    }
  }
}
```

### Confirming an entity is human

Check `claims.P31` for any value whose `id` is `Q5`. Disambiguation pages have `P31=Q4167410` — these must be explicitly rejected.

### SPARQL for combined search + type filter

For disambiguation, a SPARQL query can retrieve all humans matching a name and their key properties in one round trip:

```sparql
SELECT ?item ?itemLabel ?birth ?deathLabel ?occLabel ?natLabel WHERE {
  ?item wdt:P31 wd:Q5 .
  ?item rdfs:label "{name}"@en .
  OPTIONAL { ?item wdt:P569 ?birth . }
  OPTIONAL { ?item wdt:P570 ?death . }
  OPTIONAL { ?item wdt:P106 ?occ . }
  OPTIONAL { ?item wdt:P27 ?nat . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
}
LIMIT 20
```

This is slower than `wbsearchentities` for common names but returns structured data directly. Use `wbsearchentities` for the initial candidate list, then batch-fetch with `wbgetentities` for scoring data.

## Disambiguation scoring

Score each candidate (0.0–1.0) by comparing Wikidata entity properties against the person's `existing_attributes`:

| Signal | Weight | Implementation |
|---|---|---|
| Birth year match (±1 year) | 0.35 | P569 parsed vs `date` attributes with key containing "birth" |
| Occupation keyword overlap | 0.25 | P106 English labels vs `text` attribute values (case-insensitive token match) |
| Nationality/citizenship match | 0.20 | P27 English label vs `location` attribute country fields |
| Name alias match | 0.15 | Wikidata aliases (all languages) vs PersonName.full_name values |
| Wikipedia article exists | 0.05 | Presence of `sitelinks.enwiki` |

**Decision rules:**
- `score ≥ 0.85` AND exactly one candidate above threshold → **auto-link** (attributes written at `confidence=0.75`; `WikidataCandidateReview(status="auto_linked")` created — see #31)
- `score ≥ 0.85` AND multiple candidates above threshold → **create `WikidataCandidateReview(status="pending")`**
- All candidates `score < 0.85` → **create `WikidataCandidateReview(status="pending")`** with top 5 candidates
- Zero candidates returned by search → `EnrichmentRun(status="no_match")`

**Confirmed QID mode:** If `enrich()` is called with `confirmed_wikidata_qid` (post-adjudication from `accepted` review) or `force_rescore=True` (after rejected auto-link rollback), skip search and scoring entirely. Fetch the entity directly. Attributes written in this mode use `confidence=0.95`.

`force_rescore=True` must cause the provider to ignore any existing `wikidata_qid` attribute on the person and perform a fresh search, avoiding immediate re-linking to the just-rejected QID.

## What the provider extracts (on successful link)

### Core attributes

| key | value_type | value | notes |
|---|---|---|---|
| `wikidata_qid` | `text` | `"Q23"` | Primary link attribute; downstream providers depend on this key |
| `wikidata_url` | `platform_url` | `"https://www.wikidata.org/wiki/Q23"` | platform=`wikidata` |
| `birth_date` | `date` | `"1732-02-22"` | From P569; skip if precision < day |
| `death_date` | `date` | `"1799-12-14"` | From P570; skip if precision < day |
| `birth_year` | `text` | `"1732"` | From P569 when precision = year only |
| `occupation` | `text` | `"politician"` | One attribute per P106 value |
| `nationality` | `text` | `"American"` | From P27 English label |
| `description` | `text` | `"1st president..."` | Wikidata short description |

### External identifier attributes

For each Wikidata property on the entity that has a corresponding enabled `ExternalIdentifierProperty` record with a `formatter_url`:

1. Build the full URL: `ext_prop.build_url(identifier_value)`
2. `get_or_create` the `ExternalPlatform` using `ext_prop.platform` FK (or slug fallback)
3. Emit `EnrichmentResult(key=ext_prop.slug, value=url, value_type="platform_url", metadata={"platform": platform.slug})`

For external identifiers **without** a `formatter_url` (raw ID values only), emit as `text` attributes: `key=ext_prop.slug, value=identifier_value, value_type="text"`.

### Name aliases

For each alias in `entity.aliases.en`:
1. Check if a `PersonName` with this `full_name` already exists for the person — skip if so
2. Infer `name_type` using `infer_name_type()` from `name_utils.py`
3. Create `PersonName(full_name=alias, name_type=..., is_primary=False, source="wikidata", confidence=0.70, provenance={...})`

### Rate limits and HTTP client

- Endpoint: `https://www.wikidata.org/w/api.php`
- Required `User-Agent` header: `PersonValidator/0.1 (greg@cannabis.observer)`
- Batch `wbgetentities` calls: up to 50 QIDs per request
- No authentication required for read-only access
- Retry on HTTP 429 and 503 with exponential backoff (3 retries, base delay 1s)
- Do not hard-code a `requests.Session` — use a shared `WikimediaHttpClient` (see below)

### `WikimediaHttpClient`

Create `src/core/enrichment/providers/wikimedia_client.py`:

```python
class WikimediaHttpClient:
    """Shared HTTP client for all Wikimedia API endpoints.

    Sets the required User-Agent, handles retries on 429/503,
    and provides methods for the Action API and SPARQL endpoint.
    """
    BASE_URL = "https://www.wikidata.org/w/api.php"
    SPARQL_URL = "https://query.wikidata.org/sparql"
    USER_AGENT = "PersonValidator/0.1 (greg@cannabis.observer)"

    def search_entities(self, name: str, limit: int = 10) -> list[dict]: ...
    def get_entities(self, qids: list[str]) -> dict[str, dict]: ...
    def sparql(self, query: str) -> list[dict]: ...
```

## Provider class

```python
class WikidataProvider(Provider):
    name = "wikidata"
    output_keys = ["wikidata_qid", "wikidata_url"]
    refresh_interval = timedelta(days=7)
    dependencies = []  # no dependencies — Round 1 provider

    AUTO_LINK_THRESHOLD = 0.85
    AUTO_LINK_CONFIDENCE      = 0.75  # attributes written on auto-link (unconfirmed)
    CONFIRMED_CONFIDENCE      = 0.95  # attributes written in confirmed QID mode
    ALIAS_CONFIDENCE          = 0.70  # PersonName aliases on auto-link
    CONFIRMED_ALIAS_CONFIDENCE = 0.80  # PersonName aliases after admin confirmation

    def __init__(self, http_client: WikimediaHttpClient | None = None) -> None: ...

    def enrich(
        self,
        person: PersonData,
        *,
        confirmed_wikidata_qid: str | None = None,
        force_rescore: bool = False,
    ) -> list[EnrichmentResult]:
        """
        Main enrichment entry point.

        confirmed_wikidata_qid: if provided, skip search and extract this QID directly
            at CONFIRMED_CONFIDENCE. Used after admin accepts a pending review.
        force_rescore: if True, ignore existing wikidata_qid attribute and perform a
            fresh search. Used after admin rejects an auto_linked review (rollback path).
        """
        ...
```

## Acceptance criteria

- [ ] `WikimediaHttpClient` in `src/core/enrichment/providers/wikimedia_client.py`
- [ ] `WikidataProvider` in `src/core/enrichment/providers/wikidata.py`
- [ ] Search → score → auto-link path: attributes written at `AUTO_LINK_CONFIDENCE`, `WikidataCandidateReview(status="auto_linked")` created (see #31)
- [ ] Search → score → ambiguous: `WikidataCandidateReview(status="pending")` created, no attributes written
- [ ] Zero candidates → `no_match` run status, no review created
- [ ] `confirmed_wikidata_qid` path: attributes at `CONFIRMED_CONFIDENCE`, no review created
- [ ] `force_rescore=True` ignores existing `wikidata_qid` attribute
- [ ] Birth date precision handling tested (day vs year vs century)
- [ ] Alias creation tested (deduplication, `infer_name_type`, `ALIAS_CONFIDENCE`)
- [ ] External identifier extraction tested (with and without `formatter_url`)
- [ ] `ExternalPlatform` auto-creation tested
- [ ] Disambiguation page (`P31=Q4167410`) filtered out
- [ ] HTTP 429 retry tested
- [ ] Integration test (marked `@pytest.mark.integration`) hits live Wikidata for a well-known person
- [ ] See #31 for confirmation/rollback behaviour tests (bump utility, rollback utility)
