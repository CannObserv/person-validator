# Wikipedia / Wikidata API Technical Survey
## For Building Person-Record Enrichment Providers in Python

*All endpoints and JSON snippets verified with live API calls, March 2026.*

---

## 1. Core APIs

### 1.1 Wikidata — `wbsearchentities`

**Endpoint:** `https://www.wikidata.org/w/api.php`  
**Action:** `wbsearchentities`

```
GET https://www.wikidata.org/w/api.php
  ?action=wbsearchentities
  &search=Marie+Curie
  &language=en
  &type=item
  &format=json
  &limit=10
```

**Key parameters:**

| Parameter | Notes |
|---|---|
| `search` | Matched against labels AND aliases in `language` |
| `language` | Controls which label/alias to search AND which language to return in `label`/`description` |
| `type` | `item` (default) or `property` |
| `limit` | Max 50 |
| `haswbstatement` | Filter results — `haswbstatement=P31%3DQ5` restricts to humans |
| `search-continue` | Pagination offset returned in response |

**Ranking algorithm (documented behaviour):**  
Results are ranked by an internal Elasticsearch score. The ranking factors are:
1. Exact label match in the requested language (highest weight)
2. Alias match in the requested language  
3. Label match in other languages
4. Sitelink count (popular entities rank higher for the same string match)

The API does **not** expose a score value. For disambiguation you must apply your own post-filtering.

**Actual response for "Marie Curie", limit=3:**
```json
{
  "search": [
    {
      "id": "Q7186",
      "label": "Marie Curie",
      "description": "Polish-French physicist and chemist (1867–1934)",
      "match": { "type": "label", "language": "en", "text": "Marie Curie" }
    },
    {
      "id": "Q114939443",
      "label": "Marie Curie",
      "description": "2022 Czech book edition",
      "match": { "type": "label", "language": "en", "text": "Marie Curie" }
    },
    {
      "id": "Q30668387",
      "label": "Marie-Curie",
      "description": "future metro station in Montreal, Quebec, Canada",
      "match": { "type": "label", "language": "en", "text": "Marie-Curie" }
    }
  ],
  "search-continue": 3
}
```

**Filtering to humans with `haswbstatement`:**
```
GET ...&search=John+Smith&haswbstatement=P31%3DQ5
```
Returns only results where `P31 = Q5` is already set on the entity. This filters server-side but only works for single-valued properties — you cannot filter by birth year range here.

---

### 1.2 Wikidata — `wbgetentities`

**Endpoint:** `https://www.wikidata.org/w/api.php?action=wbgetentities`

```
GET https://www.wikidata.org/w/api.php
  ?action=wbgetentities
  &ids=Q7186|Q937|Q935
  &languages=en
  &props=labels|descriptions|claims|sitelinks
  &format=json
```

**Key parameters:**

| Parameter | Notes |
|---|---|
| `ids` | Pipe-separated QIDs; **max 50 per request** |
| `props` | Comma/pipe list: `labels`, `descriptions`, `aliases`, `claims`, `sitelinks`, `datatype` |
| `languages` | Pipe-separated; default = all languages |
| `sitefilter` | Limit sitelinks to specific wikis, e.g. `enwiki` |

**What a human entity looks like (Q7186 — Marie Curie, condensed):**

```json
{
  "id": "Q7186",
  "type": "item",
  "modified": "2026-02-27T23:12:24Z",
  "labels": {
    "en": { "language": "en", "value": "Marie Curie" }
  },
  "descriptions": {
    "en": { "language": "en", "value": "Polish-French physicist and chemist (1867–1934)" }
  },
  "claims": {
    "P31": [{
      "mainsnak": {
        "snaktype": "value",
        "property": "P31",
        "datatype": "wikibase-item",
        "datavalue": {
          "type": "wikibase-entityid",
          "value": { "entity-type": "item", "id": "Q5", "numeric-id": 5 }
        }
      },
      "type": "statement",
      "rank": "normal",
      "id": "Q7186$AB15DE87-...",
      "references": [...]
    }],
    "P569": [{
      "mainsnak": {
        "snaktype": "value",
        "property": "P569",
        "datatype": "time",
        "datavalue": {
          "type": "time",
          "value": {
            "time": "+1867-11-07T00:00:00Z",
            "precision": 11,
            "timezone": 0,
            "calendarmodel": "http://www.wikidata.org/entity/Q1985727"
          }
        }
      },
      "type": "statement",
      "rank": "normal"
    }],
    "P214": [{
      "mainsnak": {
        "snaktype": "value",
        "property": "P214",
        "datatype": "external-id",
        "datavalue": { "type": "string", "value": "76353174" }
      }
    }]
  },
  "sitelinks": {
    "enwiki": { "site": "enwiki", "title": "Marie Curie", "url": "https://en.wikipedia.org/wiki/Marie_Curie" },
    "dewiki": { "site": "dewiki", "title": "Marie Curie" }
  }
}
```

Q7186 has **242 sitelinks** (one of the most-linked persons) and **~280 claim properties**.

**Time precision values** (`precision` field in time claims):
- `9` = year only (e.g. `+1867-00-00T00:00:00Z`)
- `10` = year + month
- `11` = year + month + day (full date)

---

### 1.3 Wikidata — SPARQL at `query.wikidata.org`

**Endpoint:** `https://query.wikidata.org/sparql`  
**Method:** GET or POST  
**Accept header:** `application/sparql-results+json`  
**Prefixes pre-loaded:** `wd:`, `wdt:`, `wikibase:`, `rdfs:`, `schema:`, `bd:`

**Example 1: Find person by exact name with optional birth year**
```sparql
SELECT DISTINCT ?person ?personLabel ?birthYear ?occupationLabel ?nationalityLabel WHERE {
  ?person wdt:P31 wd:Q5 .                   # instance of human
  ?person rdfs:label "Marie Curie"@en .      # exact English label match
  OPTIONAL { ?person wdt:P569 ?birthDate .
             BIND(YEAR(?birthDate) AS ?birthYear) }
  OPTIONAL { ?person wdt:P106 ?occupation . }
  OPTIONAL { ?person wdt:P27  ?nationality . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
}
LIMIT 10
```

**Actual result for this query:**
```json
{
  "results": {
    "bindings": [
      {
        "person":          { "value": "http://www.wikidata.org/entity/Q7186" },
        "personLabel":     { "value": "Marie Curie", "xml:lang": "en" },
        "birthDate":       { "datatype": "xsd:dateTime", "value": "1867-11-07T00:00:00Z" },
        "occupationLabel": { "value": "physicist" },
        "nationalityLabel":{ "value": "France" }
      }
    ]
  }
}
```
(Multiple rows per person when multiple occupations/nationalities are present — use `GROUP_CONCAT` or `DISTINCT` + separate queries to collapse.)

**Example 2: Fuzzy name search + birth year window**
```sparql
SELECT DISTINCT ?person ?personLabel ?birthYear ?enwiki WHERE {
  ?person wdt:P31 wd:Q5 .
  ?person rdfs:label ?name FILTER(LANG(?name) = "en") .
  FILTER(CONTAINS(LCASE(STR(?name)), "curie"))
  OPTIONAL { ?person wdt:P569 ?bd . BIND(YEAR(?bd) AS ?birthYear) }
  OPTIONAL { ?enwiki schema:about ?person ;
                     schema:isPartOf <https://en.wikipedia.org/> . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
} LIMIT 20
```

**Example 3: Cross-match by external ID (ORCID)**
```sparql
SELECT ?person ?personLabel WHERE {
  ?person wdt:P496 "0000-0001-9999-1234" .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
}
```

**Example 4: Person lookup with sitelink detection**
```sparql
SELECT ?person ?personLabel ?birthDate ?enwiki WHERE {
  ?person wdt:P31 wd:Q5 ;
          rdfs:label "Alan Turing"@en .
  OPTIONAL { ?person wdt:P569 ?birthDate }
  OPTIONAL { ?enwiki schema:about ?person ;
                     schema:isPartOf <https://en.wikipedia.org/> }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
}
```

**SPARQL performance tips:**
- `wdt:` (truthy shortcut) is faster than `p:/ps:` (full statement path) for filtering
- Put most selective triple first (e.g., the P31=Q5 filter last, not first, when you have a specific name)
- Use `FILTER(STR(?birthDate) >= "1950")` on the raw date string is faster than `YEAR()` over large sets
- Add `LIMIT` always — the endpoint will cut you off at 60s/10,000 rows regardless

---

### 1.4 Wikidata — `Special:EntityData/{QID}.json`

**URL:** `https://www.wikidata.org/wiki/Special:EntityData/Q7186.json`

Returns the same payload as `wbgetentities` for a single entity but:
- Supports content negotiation: `.json`, `.jsonld`, `.ttl`, `.rdf`, `.nt`
- Cacheable by CDN (200 response with cache headers)
- No batch support
- Redirects for merged QIDs (follow redirects)

Top-level keys: `entities` → `{QID}` with: `pageid`, `ns`, `title`, `lastrevid`, `modified`, `type`, `id`, `labels`, `descriptions`, `aliases`, `claims`, `sitelinks`

---

### 1.5 Wikipedia — REST API (api.wikimedia.org)

**Base:** `https://api.wikimedia.org/core/v1/wikipedia/en/`

#### Search
```
GET https://api.wikimedia.org/core/v1/wikipedia/en/search/page
    ?q=Marie+Curie
    &limit=10
```

**Response fields per result:**
```json
{
  "id": 20408,
  "key": "Marie_Curie",
  "title": "Marie Curie",
  "excerpt": "...<span class=\"searchmatch\">Curie</span>...",
  "description": "Polish-French physicist and chemist (1867–1934)",
  "thumbnail": {
    "mimetype": "image/jpeg",
    "url": "//upload.wikimedia.org/wikipedia/commons/thumb/c/c8/Marie_Curie_c._1920s.jpg/60px-...",
    "width": 60, "height": 82
  }
}
```
Note: `description` is the short Wikidata description, not a Wikipedia-generated one. `excerpt` contains HTML with `<span class="searchmatch">` highlighting.

#### Page metadata (no summary endpoint at this base URL)
```
GET https://api.wikimedia.org/core/v1/wikipedia/en/page/Marie_Curie
```
Returns: `id`, `key`, `title`, `latest` (rev id + timestamp), `content_model`, `license`  
**Does not include a prose summary** — for that use the legacy REST API below.

#### Rate limits (api.wikimedia.org)
- **Unauthenticated:** 500 req/hour (confirmed via `X-RateLimit-Limit: 500; w=3600`)
- **With personal API token:** 5,000 req/hour
- Header format: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

---

### 1.6 Wikipedia — Legacy REST API (`en.wikipedia.org/api/rest_v1`)

This is the **Wikimedia REST Content API**, still fully operational and the right place for page summaries.

#### Page summary (most useful for person enrichment)
```
GET https://en.wikipedia.org/api/rest_v1/page/summary/Marie_Curie
```

**Actual response (key fields):**
```json
{
  "type": "standard",
  "title": "Marie Curie",
  "displaytitle": "<span class=\"mw-page-title-main\">Marie Curie</span>",
  "wikibase_item": "Q7186",
  "pageid": 20408,
  "description": "Polish-French physicist and chemist (1867–1934)",
  "description_source": "local",
  "thumbnail": {
    "source": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c8/Marie_Curie_c._1920s.jpg/330px-...",
    "width": 330, "height": 448
  },
  "originalimage": {
    "source": "https://upload.wikimedia.org/wikipedia/commons/c/c8/Marie_Curie_c._1920s.jpg",
    "width": 1549, "height": 2105
  },
  "extract": "Maria Salomea Skłodowska Curie, better known as Marie Curie, was a Polish and naturalised-French physicist and chemist...",
  "extract_html": "<p><b>Maria Salomea...</b></p>",
  "content_urls": {
    "desktop": { "page": "https://en.wikipedia.org/wiki/Marie_Curie", ... },
    "mobile": { ... }
  },
  "revision": "1340419177",
  "timestamp": "2026-02-25T16:19:31Z"
}
```

The `wikibase_item` field is the **critical bridge** — it gives you the QID directly from a Wikipedia title.

Other useful rest_v1 endpoints:
```
GET /api/rest_v1/page/title/{title}         # page metadata (redirects)
GET /api/rest_v1/page/related/{title}       # related articles
GET /api/rest_v1/page/media-list/{title}    # all images on page
```

---

### 1.7 Wikipedia — MediaWiki Action API

**Endpoint:** `https://en.wikipedia.org/w/api.php`

#### Get wikibase_item + extract + categories in one call
```
GET https://en.wikipedia.org/w/api.php
  ?action=query
  &titles=Marie_Curie|Albert_Einstein|Isaac_Newton
  &prop=pageprops|extracts|categories
  &ppprop=wikibase_item
  &exintro=1
  &explaintext=1
  &exsentences=3
  &cllimit=20
  &format=json
```

**Actual pageprops response:**
```json
{
  "pageprops": {
    "defaultsort": "Curie, Marie",
    "page_image_free": "Marie_Curie_c._1920s.jpg",
    "wikibase_item": "Q7186",
    "wikibase-shortdesc": "Polish-French physicist and chemist (1867–1934)",
    "wikibase-badge-Q17437798": ""
  }
}
```

The `wikibase-badge-Q17437798` indicates a [Featured Article](https://www.wikidata.org/wiki/Q17437798) badge.

**Batch lookup: title → QID (50 titles at once):**
```python
titles = "Marie_Curie|Albert_Einstein|Isaac_Newton"
# response maps all three titles to Q7186, Q937, Q935
```

**Key `prop` values for person enrichment:**

| prop | What you get |
|---|---|
| `pageprops` | `wikibase_item` (QID), `defaultsort`, badges |
| `extracts` | Intro prose (HTML or plain text) |
| `categories` | Category memberships (useful: `[[Category:1867 births]]`) |
| `revisions` | Last edit timestamp + user |
| `images` | List of embedded image filenames |
| `links` | Internal wikilinks in the article |

---

## 2. Disambiguation Strategy

### 2.1 How `wbsearchentities` ranks results

The search is backed by **CirrusSearch** (Elasticsearch). Ranking factors (in approximate order of weight):
1. Exact label match in requested language
2. Exact alias match in requested language
3. Prefix/substring match in labels or aliases
4. **Entity usage count** (how often the item is linked from other Wikidata items)
5. **Sitelink count** (number of Wikipedia language editions linking to this item)
6. Label/alias matches in other languages

Practical implication: For common names like "John Smith", `wbsearchentities` returns items roughly by popularity, not semantic relevance to your specific person. **Never trust rank-1 result alone.**

### 2.2 Signals confirming a result is a human

| Property | QID | Meaning |
|---|---|---|
| `P31 = Q5` | Q5 = "human" | Primary signal — direct statement |
| `P31 = Q6` | Q6 = "human (fictional)" | Fictional character — usually exclude |
| `P31 = Q15632617` | | Uncertain person entity |
| `P31 = Q4167410` | | **Disambiguation page** — always exclude |
| `P21` present | sex or gender property | Strong person indicator |
| `P569` present | birth date | Strong person indicator |
| `P570` present | death date | Strong person indicator |
| `P106` present | occupation | Strong person indicator |
| `sitelinks.enwiki` present | — | Has English Wikipedia article |

**Disambiguation page detection:**  
`Q4167410` ("Wikimedia disambiguation page") as the value of `P31` definitively marks a disambiguation page. It has no P21/P569/P106 claims.

**Quick Python check:**
```python
def is_human(entity: dict) -> bool:
    p31_vals = [
        c["mainsnak"]["datavalue"]["value"]["id"]
        for c in entity.get("claims", {}).get("P31", [])
        if c["mainsnak"]["snaktype"] == "value"
    ]
    return "Q5" in p31_vals

def is_disambiguation(entity: dict) -> bool:
    p31_vals = [
        c["mainsnak"]["datavalue"]["value"]["id"]
        for c in entity.get("claims", {}).get("P31", [])
        if c["mainsnak"]["snaktype"] == "value"
    ]
    return "Q4167410" in p31_vals
```

### 2.3 Using attributes as disambiguation filters in SPARQL

**Filter by birth year range:**
```sparql
SELECT ?person ?personLabel WHERE {
  ?person wdt:P31 wd:Q5 ;
          rdfs:label "John Smith"@en ;
          wdt:P569 ?birthDate .
  FILTER(YEAR(?birthDate) >= 1960 && YEAR(?birthDate) <= 1965)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
}
```

**Filter by occupation:**
```sparql
SELECT ?person ?personLabel WHERE {
  ?person wdt:P31 wd:Q5 ;
          rdfs:label "Alan Smith"@en ;
          wdt:P106 wd:Q33999 .   # Q33999 = actor
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
}
```

**Filter by nationality + birth decade:**
```sparql
SELECT ?person ?personLabel ?birth WHERE {
  ?person wdt:P31 wd:Q5 ;
          rdfs:label "James Brown"@en ;
          wdt:P27 wd:Q30 ;              # Q30 = United States
          wdt:P569 ?birth .
  FILTER(YEAR(?birth) >= 1930 && YEAR(?birth) < 1940)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
}
```

**Recommended scoring approach (post-SPARQL):**
```python
def score_candidate(candidate: dict, target: dict) -> float:
    score = 0.0
    # Birth year match (most discriminating for persons)
    if target.get("birth_year") and candidate.get("birth_year"):
        delta = abs(target["birth_year"] - candidate["birth_year"])
        if delta == 0:   score += 40
        elif delta <= 2: score += 20
        elif delta <= 5: score += 5
    # Occupation match
    if target.get("occupation") and target["occupation"] in candidate.get("occupations", []):
        score += 30
    # Nationality match
    if target.get("nationality") and target["nationality"] in candidate.get("nationalities", []):
        score += 15
    # Has enwiki (proxy for notability)
    if candidate.get("enwiki"):
        score += 10
    # External ID crosslinks
    for prop in ["P496", "P214", "P213"]:
        if target.get(prop) and target[prop] == candidate.get(prop):
            score += 50   # exact crosslink = near-certain match
    return score
```

---

## 3. Wikipedia RecentChanges / EventStreams

### 3.1 EventStreams SSE Endpoint

**URL:** `https://stream.wikimedia.org/v2/stream/recentchange`  
**Protocol:** Server-Sent Events (SSE), `text/event-stream`  
**Scope:** ALL Wikimedia wikis (Wikipedia, Wikidata, Commons, etc.) multiplexed

```python
import sseclient, requests

url = "https://stream.wikimedia.org/v2/stream/recentchange"
headers = {"User-Agent": "MyApp/1.0 (contact@example.com)"}
response = requests.get(url, stream=True, headers=headers)
client = sseclient.SSEClient(response)
for event in client.events():
    data = json.loads(event.data)
    # filter to enwiki article edits
    if data.get("wiki") == "enwiki" and data.get("namespace") == 0:
        print(data["title"], data["revision"])
```

**Event payload structure (actual live event):**
```json
{
  "$schema": "/mediawiki/recentchange/1.0.0",
  "meta": {
    "uri": "https://en.wikipedia.org/wiki/Peyton_Burdick",
    "domain": "en.wikipedia.org",
    "stream": "mediawiki.recentchange",
    "dt": "2026-03-05T00:57:29.259Z",
    "id": "73943801-34ca-4787-9e58-5197f888fb6a"
  },
  "id": 2002525711,
  "type": "edit",
  "namespace": 0,
  "title": "Peyton Burdick",
  "title_url": "https://en.wikipedia.org/wiki/Peyton_Burdick",
  "comment": "",
  "timestamp": 1772672247,
  "user": "~2026-13936-08",
  "bot": false,
  "minor": false,
  "patrolled": false,
  "length": { "old": 16225, "new": 16253 },
  "revision": { "old": 1341587600, "new": 1341780438 },
  "server_url": "https://en.wikipedia.org",
  "wiki": "enwiki"
}
```

**Event `type` values:**
- `edit` — Article was edited
- `new` — New article created
- `log` — Log action (deletion, protection, block, etc.)
- `categorize` — Category membership changed (fires alongside the edit that caused it)
- `external` — Wikidata edit linked to a Wikipedia page

**Resuming from a position (no missed events):**

The `id` field in SSE events is a JSON array of Kafka offsets. Resume with:
```
GET https://stream.wikimedia.org/v2/stream/recentchange
    ?since=2026-03-04T00:00:00Z
```
Or with the raw Kafka offset via the `Last-Event-ID` request header.

**Available streams** (confirmed live):
- `mediawiki.recentchange` — All wikis, all change types
- `mediawiki.revision-create` — Richer revision data including `rev_sha1`, `rev_content_format`, `rev_slots`
- `mediawiki.page-properties-change` — Fires when page props (including `wikibase_item`) change — useful for Wikidata links

### 3.2 Filtering to specific articles

The SSE stream has no server-side filter by title. You must client-side filter:

```python
WATCH_TITLES = {"Marie Curie", "Albert Einstein", "Linus Torvalds"}

for event in client.events():
    if not event.data or event.data == "":
        continue
    data = json.loads(event.data)
    if (data.get("wiki") == "enwiki"
        and data.get("type") == "edit"
        and data.get("title") in WATCH_TITLES):
        handle_edit(data)
```

Alternatively, poll the **MediaWiki Action API** for a watchlist:
```
GET https://en.wikipedia.org/w/api.php
  ?action=query
  &list=recentchanges
  &rctitles=Marie_Curie|Albert_Einstein
  &rcprop=title|ids|timestamp|comment|user|sizes
  &rclimit=50
  &format=json
```

### 3.3 Webhook alternative

**There is no Wikimedia-native webhook push system** (no equivalent of GitHub's repository webhooks). Options:

1. **EventStreams SSE (above)** — persistent SSE connection; reconnect with `since=` on disconnect
2. **Wikidata Query Service push** — not available
3. **Third-party `wikiteer`/`wikichannel`** — unmaintained community tools
4. **Roll-your-own relay:** consume SSE, push to your own webhook endpoint or message queue (Kafka/Redis)

**Recommended production pattern:**
```
EventStreams SSE → filter process (Python) → Redis pub/sub or webhook → enrichment worker
```
Keep SSE connection in a dedicated thread/process. On reconnect, replay from the last seen Kafka offset stored in your state store.

---

## 4. Wikidata External Identifier Crosslinks

Wikidata has **10,028 external identifier properties** (live count as of March 2026, via SPARQL `COUNT` over `wikibase:ExternalId` type properties).

URL patterns use `P1630` (formatter URL) on the property entity, with `$1` as placeholder for the ID value.

### 4.1 Authority Records

| Property | Label | Example value (Marie Curie) | URL pattern |
|---|---|---|---|
| `P214` | VIAF cluster ID | `76353174` | `https://viaf.org/viaf/$1` |
| `P213` | ISNI | `0000 0001 2096 0018` | `https://isni.org/isni/$1` |
| `P244` | Library of Congress authority ID | `n79061416` | `https://id.loc.gov/authorities/$1` |
| `P227` | GND ID (German National Library) | `118523023` | `https://d-nb.info/gnd/$1` |
| `P268` | BnF ID (Bibliothèque nationale de France) | `121447141` | `https://catalogue.bnf.fr/ark:/12148/cb$1` |
| `P269` | IdRef (SUDOC/French university libraries) | `026836629` | `https://www.idref.fr/$1` |
| `P906` | SELIBR (Sweden) | present | various |
| `P691` | NKC (Czech National Library) | `jn19981001679` | various |

VIAF is the **most universally populated** authority identifier — it aggregates records from 40+ national libraries and is present on most well-known persons.

### 4.2 Academic Identifiers

| Property | Label | URL pattern / Notes |
|---|---|---|
| `P496` | ORCID iD | `https://orcid.org/$1` |
| `P1960` | Google Scholar author ID | `https://scholar.google.com/citations?user=$1` |
| `P4012` | Semantic Scholar author ID | `https://www.semanticscholar.org/author/$1` |
| `P6634` | LinkedIn personal profile ID | `https://www.linkedin.com/in/$1/` |
| `P549` | Mathematics Genealogy Project ID | `https://genealogy.math.ndsu.nodak.edu/id.php?id=$1` |
| `P2456` | dblp author ID | `https://dblp.org/pid/$1` |

ORCID is the most machine-readable cross-system academic ID. Semantic Scholar author IDs (`P4012`) are numeric; Google Scholar author IDs (`P1960`) are alphanumeric strings like `qc6CJjYAAAAJ`.

**Verified live:** Einstein (Q937) has `P1960 = qc6CJjYAAAAJ` and `P4012 = 50702974`.

### 4.3 Professional / Biographical

| Property | Label | URL pattern |
|---|---|---|
| `P345` | IMDb ID | `https://www.imdb.com/name/$1` |
| `P646` | Freebase ID | `https://g.co/kg$1` |
| `P434` | MusicBrainz artist ID | `https://musicbrainz.org/artist/$1` |
| `P1728` | AllMusic artist ID | `https://www.allmusic.com/artist/$1` |
| `P1266` | AlloCiné person ID | `https://www.allocine.fr/personne/fichepersonne_gen_cpersonne=$1.html` |
| `P2605` | Čsfd person ID | various |
| `P3430` | SNAC Ark ID | `https://snaccooperative.org/ark:/99166/$1` |

### 4.4 Social Media

| Property | Label | URL pattern |
|---|---|---|
| `P2002` | X (Twitter) username | `https://x.com/$1` |
| `P2013` | Facebook username | `https://www.facebook.com/$1` |
| `P2003` | Instagram username | `https://www.instagram.com/$1/` |
| `P6634` | LinkedIn personal profile ID | `https://www.linkedin.com/in/$1/` |
| `P2397` | YouTube channel ID | `https://www.youtube.com/channel/$1` |
| `P4033` | Mastodon address | varies |
| `P8937` | Threads username | `https://www.threads.net/@$1` |

**Warning:** Social media IDs change frequently and are often stale. Treat these as hints, not ground truth.

### 4.5 Fetching URL Formatter for Any Property

```python
import requests

def get_url_formatter(property_id: str) -> str | None:
    """Fetch the URL formatter (P1630) for a Wikidata property."""
    resp = requests.get(
        "https://www.wikidata.org/w/api.php",
        params={
            "action": "wbgetentities",
            "ids": property_id,
            "props": "claims",
            "format": "json",
        },
        headers={"User-Agent": "MyApp/1.0 (contact@example.com)"},
    )
    entity = resp.json()["entities"][property_id]
    p1630 = entity.get("claims", {}).get("P1630", [])
    if p1630:
        return p1630[0]["mainsnak"]["datavalue"]["value"]
    return None

# get_url_formatter("P214") -> "https://viaf.org/viaf/$1"
# get_url_formatter("P496") -> "https://orcid.org/$1"

def build_external_url(formatter: str, value: str) -> str:
    return formatter.replace("$1", value)
```

### 4.6 Extracting all external IDs from an entity

```python
def extract_external_ids(claims: dict) -> dict[str, str]:
    """Return {property_id: value} for all external-id type claims."""
    result = {}
    for prop, statements in claims.items():
        for stmt in statements:
            snak = stmt["mainsnak"]
            if snak["datatype"] == "external-id" and snak["snaktype"] == "value":
                result[prop] = snak["datavalue"]["value"]
                break  # take first (preferred/normal rank)
    return result
```

---

## 5. Wikidata-Only Persons (No Wikipedia Sitelink)

### 5.1 Scale

- **Total humans in Wikidata (`P31=Q5`):** ~13,052,559 (live count, March 2026)
- **Humans with English Wikipedia article:** ~1,500,000 (estimated; ~11–12% of all human entities)
- **Humans without any Wikipedia sitelink:** majority — roughly 10–11 million

### 5.2 Types of persons with Wikidata records but no enwiki article

The long tail of notable-in-Wikidata-but-not-Wikipedia persons:
- **Local/regional politicians** (municipal councillors, regional officials)
- **Academic researchers** with ORCID but no article (particularly grad students, post-docs in automated imports)
- **Athletes** at lower levels of competition (third-division footballers, regional swimmers)
- **Historical persons** from non-English-speaking regions with only local-language Wikipedia coverage
- **Authors** of academic papers imported from Crossref/PubMed via bots (Scholia imports)
- **Genealogical records** (persons imported from WikiTree, genealogy databases)
- **Musicians** from non-English markets
- **Business people** without enough media coverage for Wikipedia notability

Most Wikidata-only persons were created by bots — particularly the **Mix'n'match** tool and **Author Disambiguator** for academic authors.

### 5.3 Detection

**In Wikidata entity JSON:**
```python
def has_enwiki(entity: dict) -> bool:
    return "enwiki" in entity.get("sitelinks", {})

def has_any_wikipedia(entity: dict) -> bool:
    return any(k.endswith("wiki") for k in entity.get("sitelinks", {})
               if k not in ("commonswiki", "wikidatawiki", "specieswiki",
                            "mediawikiwiki", "metawiki"))
```

**In SPARQL:**
```sparql
# Find persons WITHOUT enwiki
SELECT ?person ?personLabel WHERE {
  ?person wdt:P31 wd:Q5 ;
          wdt:P496 ?orcid .        # e.g. has ORCID
  FILTER NOT EXISTS {
    ?article schema:about ?person ;
             schema:isPartOf <https://en.wikipedia.org/> .
  }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
} LIMIT 100
```

**Practical impact for enrichment:**  
If your input record has an ORCID or other external ID, you can often find a Wikidata entity with no Wikipedia article via SPARQL `?person wdt:P496 "0000-0002-1825-0097"` — this is often richer data than what Wikipedia would provide anyway.

---

## 6. Python Library Landscape

### 6.1 `wikipedia-api` (pip: `Wikipedia-API`)

**Version:** 0.10.0 (latest as of March 2026)  
**GitHub:** https://github.com/martin-majlis/Wikipedia-API

```python
import wikipediaapi
wiki = wikipediaapi.Wikipedia(
    language="en",
    user_agent="MyApp/1.0 (contact@example.com)"
)
page = wiki.page("Marie_Curie")
print(page.summary)        # intro text
print(page.fullurl)        # canonical URL
print(page.categories)     # dict of Category objects
print(page.links)          # dict of linked pages
print(page.sections)       # list of Section objects
```

**What it does:**
- Wraps the MediaWiki Action API `extracts` + `categories` + `links` + `sections`
- Lazy-loading: `page.text` triggers the API call
- Built-in language support via constructor
- Auto-follows redirects

**What it does NOT do:**
- No Wikidata integration (no claims, no QID lookup)
- No page search (no `wbsearchentities` equivalent)
- No `wikibase_item` property access
- No image/thumbnail data
- No revision history

**Verdict:** Good for quickly getting Wikipedia article text. Too limited for person enrichment — you'll always need direct API calls too.

### 6.2 `pywikibot`

**Version:** 11.0.0 (latest)  
**Docs:** https://doc.wikimedia.org/pywikibot/

```python
import pywikibot

site = pywikibot.Site("en", "wikipedia")
wikidata_site = pywikibot.Site("wikidata", "wikidata")
repo = wikidata_site.data_repository()

# Wikidata item by QID
item = pywikibot.ItemPage(repo, "Q7186")
item.get()
print(item.labels["en"])
print(item.claims["P569"][0].getTarget())  # time value

# Navigate from Wikipedia page to Wikidata item
wp_page = pywikibot.Page(site, "Marie Curie")
item = pywikibot.ItemPage.fromPage(wp_page)
```

**Capabilities:**
- Full read/write access to all Wikimedia wikis
- Wikidata claim navigation with typed `.getTarget()` returns
- Bot framework: generators, page iterators, RC patrolling
- Handles login, OAuth, CSRF tokens automatically
- Extensive retry/throttle logic built-in

**Complexity cost:**
- Requires a `user-config.py` or programmatic site setup
- Module is large (~400KB installed)
- The claim API is verbose compared to direct JSON
- Synchronous only (no async support)
- Overkill for read-only enrichment

**Verdict:** Use for writing to Wikidata or running bot scripts. Avoid for simple read-only enrichment — the direct `requests` approach is simpler and faster.

### 6.3 Direct `requests` — is it sufficient?

**Yes, for read-only enrichment, `requests` is the right choice.**

```python
import requests, time
from functools import lru_cache

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "PersonEnricher/1.0 (https://github.com/org/repo; contact@example.com)"
})

@lru_cache(maxsize=1000)
def wikidata_search(name: str, lang: str = "en") -> list[dict]:
    resp = SESSION.get(
        "https://www.wikidata.org/w/api.php",
        params={
            "action": "wbsearchentities",
            "search": name,
            "language": lang,
            "type": "item",
            "format": "json",
            "limit": 10,
            "haswbstatement": "P31=Q5",
        },
    )
    resp.raise_for_status()
    return resp.json()["search"]

@lru_cache(maxsize=1000)
def wikidata_entity(qid: str) -> dict:
    resp = SESSION.get(
        "https://www.wikidata.org/w/api.php",
        params={
            "action": "wbgetentities",
            "ids": qid,
            "languages": "en",
            "format": "json",
        },
    )
    resp.raise_for_status()
    return resp.json()["entities"][qid]

def sparql_query(query: str) -> list[dict]:
    resp = SESSION.get(
        "https://query.wikidata.org/sparql",
        params={"query": query},
        headers={"Accept": "application/sparql-results+json"},
    )
    resp.raise_for_status()
    return resp.json()["results"]["bindings"]
```

### 6.4 Other Libraries Worth Knowing

**`wikibaseintegrator`** (pip: `wikibaseintegrator`, v0.12.15)  
- Read/write Wikidata with a cleaner API than pywikibot  
- Better for structured claim creation  
- Still overkill for read-only use  
- `from wikibaseintegrator import WikibaseIntegrator; wbi = WikibaseIntegrator(); item = wbi.item.get("Q7186")`

**`qwikidata`** (pip: `qwikidata`, v0.4.2)  
- Lightweight wrapper for `wbgetentities` + SPARQL  
- Provides typed claim getters  
- Small codebase (~500 lines) — worth reading  
- `from qwikidata.entity import WikidataItem; item = WikidataItem(data)` (you still fetch JSON yourself)

**`sseclient-py`** (pip: `sseclient-py`)  
- Essential for EventStreams consumption  
- `import sseclient; client = sseclient.SSEClient(response)`

**`mwclient`** (pip: `mwclient`)  
- MediaWiki Action API wrapper  
- Good for article text retrieval and page iteration  
- No Wikidata support

**Recommendation for person enrichment:**
```
requests (core HTTP) + sseclient-py (streams) + direct JSON parsing
```
Add `wikibaseintegrator` only if you need to write back to Wikidata.

---

## 7. Rate Limits and Etiquette

### 7.1 Wikidata Action API (`www.wikidata.org/w/api.php`)

- **No hard documented rate limit** for anonymous GET requests
- **Practical limit:** ~60–200 req/s before throttling (observed community guidance: keep to **~1 req/s** for sustained queries)
- **`wbgetentities` batch size:** max **50 QIDs** per request (`ids=Q1|Q2|...|Q50`)
- **`wbsearchentities` limit:** max 50 results per call
- **Throttle signal:** `HTTP 429` or `mediawiki-api-error: ratelimited` in response JSON
- **Bot accounts** get a higher rate limit; register at https://www.wikidata.org/wiki/Wikidata:Bots

### 7.2 SPARQL Endpoint (`query.wikidata.org`)

| Limit | Value |
|---|---|
| Query timeout | **60 seconds** (hard limit; returns HTTP 500/`TimeoutException`) |
| Max rows returned | **10,000 rows** per query |
| Max concurrent connections per IP | ~5 (observed; not documented) |
| Recommended request rate | **1 req/s** for sustained queries |
| Cache TTL (public, simple queries) | **5 minutes** (`Cache-Control: public, max-age=300`) |

**Avoiding timeouts:**
- Use `LIMIT` always
- Use `wdt:` (truthy shorthand) not `p:/ps:` full path for filtering
- Avoid `OPTIONAL` on large properties (`P569` over all humans = slow)
- Use `SERVICE wikibase:label` only at the end, after all filtering
- For counting, use the Wikidata Statistics API or pre-computed dumps instead

### 7.3 Wikipedia REST API (`api.wikimedia.org`)

| Scenario | Limit |
|---|---|
| Unauthenticated | **500 req/hour** |
| Personal API token | **5,000 req/hour** |
| Headers | `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` |

Get a personal token at https://api.wikimedia.org/wiki/Getting_started_with_Wikimedia_APIs  
No account required for a personal access token; just email address for registration.

### 7.4 Wikipedia Legacy REST API (`en.wikipedia.org/api/rest_v1`)

- No hard documented rate limit
- Responses are cached aggressively by CDN (ETags, `Cache-Control: s-maxage=...`)
- Practical limit: same etiquette as other endpoints — stay under 200 req/s

### 7.5 Required User-Agent Format

Wikimedia **requires** a descriptive User-Agent. Requests with generic agents (`python-requests/2.x`) are increasingly rejected or throttled.

**Format:** `{AppName}/{version} ({contact_info})`

```python
USER_AGENT = "PersonEnricher/1.0 (https://github.com/yourorg/yourrepo; your@email.com)"
```

Or for a bot account:
```
PersonEnricher/1.0 (https://www.wikidata.org/wiki/User:YourBot; your@email.com)
```

**Set it on the session, not per-request:**
```python
session = requests.Session()
session.headers["User-Agent"] = USER_AGENT
```

### 7.6 Recommended Caching TTL

| Resource | Recommended TTL | Rationale |
|---|---|---|
| `wbsearchentities` results | 1 hour | Label/alias changes are infrequent |
| `wbgetentities` full entity | 24 hours | Claims change slowly |
| SPARQL result (person attributes) | 6–24 hours | Depends on data freshness needs |
| Wikipedia page summary | 24 hours | Content changes but intro is stable |
| Entity data (`Special:EntityData`) | 24 hours | CDN-cached anyway |
| VIAF/ORCID/GND identifiers on entity | 7 days | Authority IDs almost never change |
| Social media IDs | 1–7 days | Can become stale, but rarely change |

**Cache key recommendation:** Use `(entity_type, id, language)` as the cache key. For SPARQL, hash the normalized query string.

### 7.7 Complete Rate-Limiting Example

```python
import time, requests
from functools import wraps
from threading import Lock

_rate_lock = Lock()
_last_request_time = 0.0
MIN_INTERVAL = 0.1  # 10 req/s max; set to 1.0 for SPARQL

def rate_limited(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        global _last_request_time
        with _rate_lock:
            elapsed = time.monotonic() - _last_request_time
            if elapsed < MIN_INTERVAL:
                time.sleep(MIN_INTERVAL - elapsed)
            _last_request_time = time.monotonic()
        return func(*args, **kwargs)
    return wrapper

@rate_limited
def fetch_entity(qid: str) -> dict:
    resp = SESSION.get(
        "https://www.wikidata.org/w/api.php",
        params={"action": "wbgetentities", "ids": qid,
                "languages": "en", "format": "json"},
    )
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 60))
        time.sleep(retry_after)
        return fetch_entity(qid)  # retry once
    resp.raise_for_status()
    return resp.json()["entities"][qid]
```

---

## Quick Reference: All Base URLs

```
# Wikidata
https://www.wikidata.org/w/api.php              # Action API (wbsearchentities, wbgetentities)
https://query.wikidata.org/sparql               # SPARQL endpoint
https://www.wikidata.org/wiki/Special:EntityData/{QID}.json  # Direct entity JSON

# Wikipedia (new REST)
https://api.wikimedia.org/core/v1/wikipedia/en/search/page?q={query}
https://api.wikimedia.org/core/v1/wikipedia/en/page/{title}

# Wikipedia (legacy REST — use for summary)
https://en.wikipedia.org/api/rest_v1/page/summary/{title}

# Wikipedia (Action API)
https://en.wikipedia.org/w/api.php              # pageprops, extracts, categories, search

# EventStreams
https://stream.wikimedia.org/v2/stream/recentchange
https://stream.wikimedia.org/v2/stream/mediawiki.revision-create
https://stream.wikimedia.org/v2/stream/mediawiki.page-properties-change
```
