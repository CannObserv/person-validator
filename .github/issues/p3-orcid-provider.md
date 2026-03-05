## Context

ORCID (Open Researcher and Contributor ID, `orcid.org`) provides persistent digital identifiers for researchers and academics. It is the dominant identity system in academic publishing, grant applications, and institutional repositories. An ORCID record is self-curated by the researcher and may include employment, education, peer-reviewed works, and external identifier crosslinks.

The Wikidata property **P496** stores the ORCID iD for persons with public ORCID records.

## Domain knowledge: ORCID

**What ORCID covers:**
- Active researchers in all academic disciplines
- Graduate students, postdocs, and early-career researchers
- Primarily living persons (historical figures rarely have ORCID records)

**What ORCID provides (from public profiles):**
- Preferred name (given, family, credited names)
- Other names / name variants
- Biography text (free-form, researcher-authored)
- Employment history: institution, department, role, dates
- Education history: institution, degree, dates
- Works: publications, datasets, software (with DOIs and metadata)
- External identifiers: ResearcherID, Scopus Author ID, Loop Profile, etc.
- Social/professional URLs the researcher has self-reported

**What ORCID does NOT cover:**
- Non-academic public figures
- Persons who have not registered an ORCID
- Private ORCID records (some researchers set their profiles to limited/private)

**The ORCID iD format:** 16-digit hyphen-grouped number, e.g. `0000-0001-2345-6789`. The last digit is a check digit (ISO 7064 MOD 11-2 algorithm).

## API access: Public ORCID API

No authentication required for public profiles. The public API base URL is `https://pub.orcid.org/v3.0/`.

```
GET https://pub.orcid.org/v3.0/{orcid}/record
Headers:
  Accept: application/json
  User-Agent: PersonValidator/0.1 (greg@cannabis.observer)
```

HTTP 404 → person has no ORCID record or the record is private/deleted.
HTTP 409 → ORCID is deprecated (researcher merged records).

### Response structure

```json
{
  "orcid-identifier": {"path": "0000-0001-2345-6789"},
  "person": {
    "name": {
      "given-names": {"value": "Jane"},
      "family-name": {"value": "Smith"},
      "credit-name": {"value": "J. Smith"},
      "other-names": {
        "other-name": [{"content": "Jane A. Smith"}]
      }
    },
    "biography": {"content": "Professor of..."},
    "external-identifiers": {
      "external-identifier": [
        {
          "external-id-type": "ResearcherID",
          "external-id-value": "A-1234-2008",
          "external-id-url": {"value": "https://www.researcherid.com/rid/A-1234-2008"}
        }
      ]
    },
    "researcher-urls": {
      "researcher-url": [
        {"url-name": "Lab website", "url": {"value": "https://..."}},
        {"url-name": "Google Scholar", "url": {"value": "https://scholar.google.com/..."}}
      ]
    }
  },
  "activities-summary": {
    "employments": {
      "affiliation-group": [
        {
          "summaries": [{
            "employment-summary": {
              "organization": {"name": "MIT"},
              "department-name": "EECS",
              "role-title": "Professor",
              "start-date": {"year": {"value": "2010"}},
              "end-date": null
            }
          }]
        }
      ]
    },
    "educations": {...}
  }
}
```

### ORCID record sections

Use the individual section endpoints to avoid fetching the entire record when only specific data is needed. For the initial implementation, fetch the full record in one call.

## What the provider extracts

| key | value_type | value | notes |
|---|---|---|---|
| `orcid_url` | `platform_url` | `"https://orcid.org/0000-0001-2345-6789"` | platform=`orcid` |
| `biography` | `text` | `"Professor of computational biology..."` | From `person.biography.content` |
| `employment` | `text` | `"Professor, MIT EECS (2010–present)"` | One attr per employment entry |
| `education` | `text` | `"PhD, Stanford University (2005)"` | One attr per education entry |

### Name variants from ORCID

- `credit-name` → `PersonName(name_type="professional", ...)` if not already present
- `other-names` → `PersonName(name_type="alias", ...)` for each

Provenance:
```json
{
  "provider": "orcid",
  "retrieved_at": "...",
  "orcid_id": "0000-0001-2345-6789",
  "source_url": "https://orcid.org/0000-0001-2345-6789"
}
```

### External identifiers from ORCID

ORCID records self-reported external identifiers (ResearcherID, Scopus, etc.). For each `external-identifier`:
1. Look up `external-id-type` against `ExternalIdentifierProperty` (by display name or slug)
2. If found and enabled: emit appropriate attribute (platform_url if URL present, text otherwise)

### Researcher URLs from ORCID

For each `researcher-url`, emit a `url` attribute with the researcher-provided label as the attribute key (slugified).

## Input: where to find the ORCID value

The ORCID iD is extracted from `person.existing_attributes` — look for a `platform_url` attribute whose `metadata.platform = "orcid"` (written by `WikidataProvider` from P496).

Parse the ORCID iD from the URL: last path segment of `https://orcid.org/{orcid}`.

```python
dependencies = [
    Dependency("wikidata_qid", skip_if_absent=True),
]
```

If no `platform_url` with `platform="orcid"` exists → exit with `no_match`.

## Acceptance criteria

- [ ] `ORCIDProvider` in `src/core/enrichment/providers/orcid.py`
- [ ] Reads ORCID iD from `platform_url` attribute with `metadata.platform = "orcid"`
- [ ] Fetches full record from public ORCID API
- [ ] Handles HTTP 404 (private/absent) and 409 (deprecated) gracefully
- [ ] Extracts `orcid_url`, `biography`, `employment`, `education`
- [ ] Creates `PersonName` records for `credit-name` and `other-names`
- [ ] Processes self-reported external identifiers via `ExternalIdentifierProperty`
- [ ] Processes researcher URLs as `url` attributes
- [ ] Does not duplicate attributes already present at higher confidence
- [ ] Tests use mocked HTTP with fixture JSON (cover: full record, private 404, deprecated 409)
- [ ] Integration test (marked `@pytest.mark.integration`) for a researcher with a public ORCID
