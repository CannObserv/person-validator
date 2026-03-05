## Context

VIAF (Virtual International Authority File, `viaf.org`) is operated by OCLC and aggregates authority records from 40+ national and international library systems, including the Library of Congress, British Library, Deutsche Nationalbibliothek, Bibliothèque nationale de France, and many others. For any person who has published works, held significant public roles, or been documented in a national library, VIAF is typically the richest machine-readable source of name variants, dates, and associated works.

The Wikidata property **P214** stores the VIAF cluster ID for persons with VIAF records.

## Domain knowledge: VIAF

**What VIAF covers:**
- Authors, composers, artists, academics — any person documented in a participating library's authority file
- Historical figures (going back centuries) as well as contemporary persons
- Persons notable enough to be catalogued anywhere in the world's major library systems

**What VIAF provides:**
- All authorized name forms contributed by each participating library (often in multiple languages and scripts)
- Birth and death dates (sometimes century-level precision for historical figures)
- Associated works (books, compositions, etc. attributed to this person)
- Contributor source links (e.g. the specific LC Authority record URL)
- Co-references to other identity systems (ISNI, LC, GND, BNF, etc.)

**What VIAF does NOT cover:**
- Most living persons who have not published or been formally catalogued
- Political figures without a publishing/academic record (Ballotpedia/OpenSecrets cover these better)
- Sports figures, entertainers without library cataloguing

## API access: JSON-LD REST

No authentication required. No formal rate limits documented, but OCLC requests reasonable use.

### Fetch by VIAF ID

```
GET https://viaf.org/viaf/{viaf_id}/viaf.json
Headers:
  User-Agent: PersonValidator/0.1 (greg@cannabis.observer)
  Accept: application/json
```

Example: `https://viaf.org/viaf/31996712/viaf.json` (George Washington)

### Key response fields

```json
{
  "viafID": "31996712",
  "nameType": "Personal",
  "mainHeadings": {
    "data": [
      {"text": "Washington, George, 1732-1799", "sources": {"s": ["LC", "BNF"]}}
    ]
  },
  "x400s": {
    "data": [
      {"text": "Washington, Georges, 1732-1799"},
      {"text": "Вашингтон, Джордж"}
    ]
  },
  "birthDate": "1732",
  "deathDate": "1799",
  "dateType": "lived",
  "sources": {
    "source": [
      {"text": "LC", "#text": "n79006704"},
      {"text": "DNB", "#text": "118806939"}
    ]
  },
  "ISBNs": {...},
  "titles": {"work": [...]},
  "links": {"url": [...]}
}
```

Note: VIAF JSON structure is somewhat irregular. `x400s.data` contains variant name forms. `sources.source` lists all contributing authorities with their local IDs.

### VIAF search API (independent search path)

```
GET https://viaf.org/search
  ?query=local.personalNames+all+%22George+Washington%22
  &maximumRecords=5
  &startRecord=1
  &recordSchema=http://viaf.org/BriefVIAFCluster
  &httpAccept=application/json
```

This enables a future standalone `VIAFProvider` that searches VIAF independently (without requiring Wikidata P214). Out of scope for this issue.

## What the provider extracts

| key | value_type | value | notes |
|---|---|---|---|
| `viaf_url` | `platform_url` | `"https://viaf.org/viaf/31996712"` | platform=`viaf` |
| `birth_year` | `text` | `"1732"` | From `birthDate`; skip if `birth_date` (full date) already present |
| `death_year` | `text` | `"1799"` | From `deathDate`; skip if `death_date` already present |

### Name variants from VIAF

From `x400s.data` (variant name forms contributed by participating libraries):
- Each unique text value → `PersonName` record if not already present
- `name_type`: default `alias`; apply `infer_name_type()` heuristics (non-Latin → `transliteration`, initials → `abbreviation`)
- `confidence`: `0.80`
- `provenance`:
```json
{
  "provider": "viaf",
  "retrieved_at": "...",
  "viaf_id": "31996712",
  "source_url": "https://viaf.org/viaf/31996712/"
}
```

### Cross-reference identifiers from VIAF

`sources.source` lists contributing authority files with their local IDs. For each source where the local library system has an `ExternalIdentifierProperty` record, emit a `text` attribute:

| Source code | System | Wikidata prop |
|---|---|---|
| `LC` | Library of Congress | P244 |
| `DNB` | Deutsche Nationalbibliothek (GND) | P227 |
| `BNF` | Bibliothèque nationale de France | P268 |
| `SUDOC` | SUDOC (France) | P269 |
| `NLA` | National Library of Australia | P409 |
| `SELIBR` | National Library of Sweden | P906 |

Look up the source code against `ExternalIdentifierProperty` records (by matching the subject item or a code→property mapping). If found and enabled, emit the local ID as a `text` attribute. This provides cross-reference data that other providers (future LC, GND providers) can use.

## Input: where to find the P214 value

The VIAF ID is extracted from `person.existing_attributes` where `key = "viaf-cluster-id"` (or whatever slug `ExternalIdentifierProperty` generates for P214 — the exact slug depends on the sync command output, but it will contain "viaf").

The provider should search `existing_attributes` for an attribute whose value is a VIAF URL (platform=`viaf`) or whose key matches the P214 slug pattern, rather than hardcoding a key name.

```python
dependencies = [
    Dependency("wikidata_qid", skip_if_absent=True),
]
```

Note: unlike Ballotpedia/OpenSecrets, VIAF does not require the VIAF ID to be present as a dependency — `WikidataProvider` writes the VIAF identifier as a `platform_url` attribute (not a separate key). The VIAFProvider reads the `platform_url` attribute whose `metadata.platform = "viaf"` to get the VIAF ID. If no such attribute exists, it exits with `no_match`.

## Acceptance criteria

- [ ] `VIAFProvider` in `src/core/enrichment/providers/viaf.py`
- [ ] Reads VIAF ID from `platform_url` attribute with `metadata.platform = "viaf"`
- [ ] Fetches `viaf.json` and parses correctly
- [ ] Handles irregular JSON structure (missing fields, single vs. list values)
- [ ] Extracts `viaf_url`, `birth_year`/`death_year` (with existing-attribute checks)
- [ ] Creates `PersonName` records for variant name forms (deduplication, `infer_name_type`)
- [ ] Extracts cross-reference IDs for known source codes
- [ ] Returns `no_match` when no VIAF platform_url attribute exists
- [ ] Returns `no_match` on HTTP 404 (entity not found or deleted)
- [ ] Tests use mocked HTTP with fixture JSON
- [ ] Integration test (marked `@pytest.mark.integration`) for a known author/academic
