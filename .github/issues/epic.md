## Overview

This epic tracks the design and implementation of the person record enrichment provider system, beginning with Wikipedia/Wikidata integration and expanding to authoritative identity systems linked through the semantic web.

## Background

Person Validator enriches person records with data from external authoritative sources. This epic establishes the full provider framework and implements the first set of providers, anchored on Wikidata as the hub of the semantic web identity graph.

### Why Wikidata first

Wikidata (wikidata.org) is a free, machine-readable knowledge graph operated by the Wikimedia Foundation. Every person entity in Wikidata carries:
- Structured biographical facts (birth/death dates, occupation, nationality)
- A stable QID (e.g. `Q23`) that serves as a universal identifier
- Links to dozens of external authoritative identity systems via external identifier properties (P214 for VIAF, P496 for ORCID, P2390 for Ballotpedia, P4386 for OpenSecrets, etc.)
- Aliases in multiple languages and scripts
- A sitelink to the corresponding Wikipedia article (when one exists)

A single Wikidata entity can yield the identifier keys needed to query VIAF, ORCID, Ballotpedia, OpenSecrets, Library of Congress, GND, IMDb, MusicBrainz, and ~2,394 other identity systems. This makes Wikidata the natural foundation for a cascading enrichment system.

### Architecture summary

Providers execute in **dependency-resolved rounds**:
- **Round 1 (parallel):** WikidataProvider — no dependencies
- **Round 2 (parallel):** WikipediaProvider, VIAFProvider, ORCIDProvider, BallotpediaProvider, OpenSecretsProvider — all depend on `wikidata_qid`

When WikidataProvider cannot auto-link (ambiguous or low-confidence match), it creates a `WikidataCandidateReview` record for human adjudication in the Django admin. Accepting a candidate immediately triggers full downstream enrichment.

### Wikidata external identifier taxonomy

Wikidata contains 10,028 external identifier properties. 2,394 apply to human persons (Q5). These are imported into the `ExternalIdentifierProperty` model and exposed in Django admin for administrative narrowing. WikidataProvider consults this table at runtime to extract and construct URLs for all enabled identifiers — no hardcoded allowlist.

### Confidence convention

| Link method | Confidence |
|---|---|
| Auto-linked (unambiguous Wikidata match) | 0.75 |
| Human-adjudicated (admin accepted) | 0.95 |
| Derived from confirmed Wikidata identifier | 0.90 |
| Downstream provider data (VIAF facts, ORCID record) | 0.85 |
| Name alias from Wikidata | 0.70 |

## Implementation phases

### Phase 0 — Foundation

Prerequisites for all providers. No user-visible enrichment output yet.

- #15: Rename `SocialPlatform` → `ExternalPlatform`
- #16: Add `confidence` + `provenance` to `PersonName`
- #17: `EnrichmentRun` audit log model
- #18: `ExternalIdentifierProperty` model + `sync_wikidata_properties` command
- #19: Redesign `EnrichmentRunner` (dependency graph, parallel execution)

### Phase 1 — WikidataProvider

- #20: `WikidataCandidateReview` model + post-save signal
- #21: `WikidataProvider` implementation
- #22: Django admin adjudication UI

### Phase 2 — WikipediaProvider

- #23: `WikipediaProvider` implementation

### Phase 3 — Priority Providers (in order)

- #24: `BallotpediaProvider`
- #25: `OpenSecretsProvider`
- #26: `VIAFProvider`
- #27: `ORCIDProvider`

### Phase 4 — Cron Infrastructure

- #28: `run_enrichment_cron` command + systemd timer units

## Future providers (researched, not yet scheduled)

| Provider | Wikidata Prop | Coverage | Notes |
|---|---|---|---|
| ISNI | P213 | Authors, performers, public figures | Free REST API; complements VIAF |
| Library of Congress | P244 | US-catalogued persons | id.loc.gov JSON API |
| GND (lobid.org) | P227 | European academics & cultural figures | SPARQL federation from Wikidata works |
| MusicBrainz | P434 | Musicians, composers, producers | Rich open API; no auth required |
| IMDb | P345 | Film/TV persons | SPARQL federation via QLever confirmed working |
| Semantic Scholar | P7924 | Academic researchers | Free REST API |
| SNAC | P3430 | Archival identity records | Free REST API |

### SPARQL federation capability (future optimization)

Research confirmed that the Wikidata SPARQL endpoint supports `SERVICE{}` federation to:
- **GND (lobid.org):** `SERVICE <https://lobid.org/gnd/search>` — returns GND biographical data
- **IMDb (QLever):** `SERVICE <https://qlever.dev/api/imdb>` — returns IMDb person data including birth year and professions

Future providers for these sources may use federated SPARQL queries rather than separate HTTP clients.

## Design document

Full design rationale, data models, API details, and all decisions: `DESIGN-ENRICHMENT-PROVIDERS.md` in the repository root.
