## Context

Ballotpedia is the primary reference for US elected officials and candidates at federal, state, and many local levels. It covers not only current officeholders but historical figures and primary/general election candidates. The Wikidata property **P2390** stores the Ballotpedia page slug for persons with Ballotpedia articles.

This is the highest-priority downstream provider because its coverage is narrowly defined (US political figures), its data is highly structured, and the API is freely accessible.

## Domain knowledge: Ballotpedia

**What Ballotpedia covers:**
- All US federal officeholders and candidates (Congress, President, VP, Senate)
- All US state legislative officeholders and candidates
- Statewide officials (governors, AGs, secretaries of state, etc.)
- Many county/municipal officials in larger jurisdictions
- Ballot measure advocates (limited)

**What it does NOT cover:**
- International political figures
- US figures who have never run for or held office
- Most local offices below county level

**Data available per person page:**
- Full name, party affiliation
- All offices held (title, jurisdiction, district, start/end dates)
- Election history (year, office sought, outcome, vote %, opponent)
- Committee assignments (for legislators)
- Biographical: birth date, education, prior career
- Contact info: official website, social media (when public)
- Campaign finance summary (sourced from FEC data)

## API access: MediaWiki Action API

Ballotpedia runs on MediaWiki. The API is at:
`https://ballotpedia.org/api.php`

No API key required for read access.

### Fetching a person page by slug

The P2390 value is the Ballotpedia page title (URL slug with underscores), e.g. `"Nancy_Pelosi"`.

```
GET https://ballotpedia.org/api.php
  ?action=parse
  &page=Nancy_Pelosi
  &prop=wikitext|categories|links
  &format=json
```

Returns the raw wikitext of the article. Structured data must be extracted from infobox templates embedded in the wikitext.

### Alternative: `prop=revisions&rvprop=content`

```
GET https://ballotpedia.org/api.php
  ?action=query
  &titles=Nancy_Pelosi
  &prop=revisions
  &rvprop=content
  &format=json
```

### Parsing Ballotpedia wikitext

Ballotpedia person articles follow a consistent infobox template pattern:
```
{{Infobox officeholder
|name=Nancy Pelosi
|birth_date={{birth date|1940|3|26}}
|party=Democratic Party
|state=California
...
}}
```

A wikitext parser is needed. The `mwparserfromhell` Python library (MIT license) handles MediaWiki wikitext parsing cleanly:
```python
import mwparserfromhell
wikicode = mwparserfromhell.parse(wikitext)
templates = wikicode.filter_templates()
infobox = next((t for t in templates if "officeholder" in t.name.lower()), None)
if infobox:
    birth_date = infobox.get("birth_date").value.strip()
```

Add `mwparserfromhell` as a runtime dependency (`uv add mwparserfromhell`).

### Alternative: Ballotpedia API endpoint

Ballotpedia also exposes a structured API at:
`https://api.ballotpedia.org/` (requires API key, not publicly documented)

Do not use this — use the public MediaWiki API.

## What the provider extracts

| key | value_type | value | notes |
|---|---|---|---|
| `ballotpedia_url` | `platform_url` | `"https://ballotpedia.org/Nancy_Pelosi"` | platform=`ballotpedia` |
| `party` | `text` | `"Democratic Party"` | From infobox |
| `birth_date` | `date` | `"1940-03-26"` | Skip if already present from Wikidata |
| `office_held` | `text` | `"Speaker of the House"` | One attr per office; include dates in value |
| `state` | `text` | `"California"` | Home state |

The provider should **not** re-write attributes already present from a higher-confidence source. Check `person.existing_attributes` before emitting duplicate keys.

## Input: where to find the P2390 value

The Ballotpedia slug is extracted from `person.existing_attributes` where `key = "ballotpedia-slug"` — this attribute is written by `WikidataProvider` when it extracts the P2390 claim.

The dependency declaration:
```python
dependencies = [
    Dependency("wikidata_qid", skip_if_absent=True),
    Dependency("ballotpedia-slug", skip_if_absent=True),
]
```

Both `wikidata_qid` and `ballotpedia-slug` must be present for this provider to run. If the person has no P2390 in Wikidata, `ballotpedia-slug` will not exist and the provider will be skipped (correct behaviour — not all persons have Ballotpedia pages).

## Provider class skeleton

```python
class BallotpediaProvider(Provider):
    name = "ballotpedia"
    output_keys = ["ballotpedia_url", "party", "office_held", "state"]
    refresh_interval = timedelta(days=1)  # political data changes frequently
    dependencies = [
        Dependency("wikidata_qid", skip_if_absent=True),
        Dependency("ballotpedia-slug", skip_if_absent=True),
    ]
    BASE_URL = "https://ballotpedia.org/api.php"
    USER_AGENT = "PersonValidator/0.1 (greg@cannabis.observer)"
```

## Acceptance criteria

- [ ] `mwparserfromhell` added as runtime dependency
- [ ] `BallotpediaProvider` in `src/core/enrichment/providers/ballotpedia.py`
- [ ] Reads `ballotpedia-slug` from `person.existing_attributes`
- [ ] Fetches and parses MediaWiki wikitext
- [ ] Extracts infobox fields correctly
- [ ] Skips attribute keys already present in existing_attributes
- [ ] Returns `no_match` when page returns 404 or has no officeholder infobox
- [ ] Both dependencies declared correctly
- [ ] All paths tested with mocked HTTP and fixture wikitext
- [ ] Integration test (marked `@pytest.mark.integration`) for a known public official
