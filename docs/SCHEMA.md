# Database Schema

## Tables

| Table | App | Purpose |
|---|---|---|
| `persons_person` | persons | Identity anchor, denormalized primary name |
| `persons_personname` | persons | All name variants for a person |
| `persons_personattribute` | persons | Enrichment data (append-only EAV); `value_type` (indexed) + `metadata` (JSONField) |
| `persons_attributelabel` | persons | Controlled label vocabulary per `value_type` (e.g. "work", "home") |
| `persons_externalplatform` | persons | Controlled platform/identity vocabulary for `platform_url` attributes |
| `persons_externalidentifierproperty` | persons | Wikidata external identifier property taxonomy; used by WikidataProvider to extract and construct URLs; managed by `sync_wikidata_properties` command. **Note:** P2390 (Ballotpedia) is seeded by migration 0015 — not imported by sync (structural SPARQL filter gap). |
| `persons_enrichmentrun` | persons | Audit log of provider runs (one row per person+provider invocation); counters: `attributes_saved` (new rows), `attributes_refreshed` (updated rows), `attributes_skipped` (no-ops + failures); `attributes_created` is retired (always 0) |
| `persons_wikidatacandidatereview` | persons | Ambiguous/low-confidence Wikidata search results queued for admin review; post-save signal triggers enrichment on acceptance |
| `keys_apikey` | keys | API key hashes for FastAPI auth |

## PersonAttribute value_type Values

`text`, `email`, `phone`, `url`, `platform_url`, `location`, `date`

Defined in `src/core/enrichment/attribute_types.VALUE_TYPE_CHOICES` (imported by `models.py`).

**Labelable types** (`metadata["label"]` supported): `email`, `phone`, `url`, `platform_url`, `location`

Defined in `src/core/enrichment/attribute_types.LABELABLE_TYPES`.

## Enrichment Attribute Key Convention

Keys written by downstream providers (those depending on `wikidata_qid`) follow `{platform}-{identifier-type}`:

- **`-slug`** — human-readable URL path component (e.g. `ballotpedia-slug` → `Nancy_Pelosi`)
- **`-id`** — opaque numeric or alphanumeric identifier (e.g. `opensecrets-crp-id` → `N00007360`)

`ExternalIdentifierProperty.slug` must match the attribute key that `WikidataProvider` writes (it uses `prop.slug` directly). Keep in sync when adding providers.
