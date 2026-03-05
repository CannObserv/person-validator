## Context

`WikipediaProvider` enriches a person with their English Wikipedia article URL and a plain-text summary extract. It is a Round 2 provider: it depends on `wikidata_qid` being written by `WikidataProvider`.

The provider does **not** search Wikipedia independently. Instead it:
1. Reads the `wikidata_qid` attribute from the person
2. Fetches the Wikidata entity to get the `enwiki` sitelink (article title)
3. Fetches the article summary from the Wikimedia REST API

If no `enwiki` sitelink exists, the provider records a warning and exits with `no_match` status. This is expected and normal — roughly 50–60% of Wikidata human entities have no English Wikipedia article.

## Domain knowledge: APIs used

### Wikidata sitelink lookup

The Wikidata entity JSON (from `wbgetentities`) includes a `sitelinks` object:
```json
"sitelinks": {
  "enwiki": {"title": "George_Washington"},
  "frwiki": {"title": "George Washington"},
  ...
}
```

The provider fetches the entity using the shared `WikimediaHttpClient.get_entities([qid])` method (already implemented in the WikidataProvider issue).

### Wikipedia REST API — page summary

```
GET https://api.wikimedia.org/core/v1/wikipedia/en/page/{title}/summary
Headers:
  User-Agent: PersonValidator/0.1 (greg@cannabis.observer)
  Authorization: (none required for public pages)
```

Response shape (abbreviated):
```json
{
  "title": "George_Washington",
  "displaytitle": "George Washington",
  "description": "1st president of the United States",
  "extract": "George Washington (February 22, 1732 – December 14, 1799) was...",
  "content_urls": {
    "desktop": {"page": "https://en.wikipedia.org/wiki/George_Washington"}
  },
  "thumbnail": {
    "source": "https://upload.wikimedia.org/wikipedia/commons/thumb/.../200px-...",
    "width": 200,
    "height": 251
  }
}
```

The `extract` field is a plain-text summary (no HTML). It is typically 1–3 paragraphs.

Title encoding: spaces in article titles are represented as underscores in the URL. The sitelink title from Wikidata already uses this format.

HTTP 404 means the article was deleted or the title changed — treat as `no_match` with a warning.

## What the provider extracts

| key | value_type | value | notes |
|---|---|---|---|
| `wikipedia_url` | `platform_url` | `"https://en.wikipedia.org/wiki/George_Washington"` | platform=`wikipedia` |
| `wikipedia_extract` | `text` | `"George Washington (February 22...)"` | Full extract from REST API |

Confidence for both attributes: `0.90` (derived from confirmed Wikidata entity).

## Provider class

```python
class WikipediaProvider(Provider):
    name = "wikipedia"
    output_keys = ["wikipedia_url", "wikipedia_extract"]
    refresh_interval = timedelta(days=7)
    dependencies = [
        Dependency("wikidata_qid", skip_if_absent=True),
    ]

    def enrich(self, person: PersonData) -> list[EnrichmentResult]:
        qid = next(
            (a["value"] for a in person.existing_attributes if a["key"] == "wikidata_qid"),
            None,
        )
        # fetch entity → get enwiki sitelink → fetch summary → return results
        ...
```

## Acceptance criteria

- [ ] `WikipediaProvider` in `src/core/enrichment/providers/wikipedia.py`
- [ ] Reads `wikidata_qid` from `person.existing_attributes`
- [ ] Returns `no_match` run status (via empty result + warning) when no `enwiki` sitelink
- [ ] Returns `no_match` when Wikipedia REST API returns 404
- [ ] Extracts `wikipedia_url` and `wikipedia_extract` correctly
- [ ] Uses `WikimediaHttpClient` (not a separate `requests.Session`)
- [ ] `platform=wikipedia` set on `platform_url` attribute
- [ ] `Dependency("wikidata_qid", skip_if_absent=True)` declared
- [ ] All paths tested with mocked HTTP
- [ ] Integration test (marked `@pytest.mark.integration`) for a known public figure
