## Context

`SocialPlatform` was originally conceived as a controlled vocabulary for social media profile links (`platform_url` attributes). The scope has expanded: we now want to track authoritative identity system URLs — Wikidata, VIAF, ORCID, Library of Congress, etc. — which are not social platforms. The name is misleading and must be corrected before enrichment providers are built.

## What to change

### Model rename

`SocialPlatform` → `ExternalPlatform` everywhere:

- `src/web/persons/models.py`: rename class, update `db_table = "persons_externalplatform"`, update docstring
- `src/web/persons/admin.py`: rename import, registration, class name
- `src/core/enrichment/runner.py`: rename `_load_active_platforms()` import (`SocialPlatform` → `ExternalPlatform`); update all references
- `src/core/enrichment/__init__.py`: update re-exports if any
- `src/core/enrichment/base.py`: no changes expected
- All test files referencing `SocialPlatform`

### Migration

Create a Django migration that:
1. Renames the table `persons_socialplatform` → `persons_externalplatform` using `migrations.RenameModel` (which handles the table rename, FK references, and content types automatically)

### New default platform seeds

Create a **new data migration** (separate from the rename migration) that seeds the following additional `ExternalPlatform` records. These complement the existing social platforms (`linkedin`, `github`, `twitter`, `instagram`, `facebook`, `youtube`, `tiktok`):

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

## TDD approach

1. Write tests that import and use `ExternalPlatform` (they will fail with `ImportError` initially)
2. Rename the model and run migrations
3. Update all imports

## Acceptance criteria

- [ ] `SocialPlatform` name does not appear anywhere in the codebase except migration history files
- [ ] `ExternalPlatform` model exists at `src/web/persons/models.py`
- [ ] DB table is `persons_externalplatform`
- [ ] All existing tests pass
- [ ] New default platforms seeded (verified by test on the data migration)
- [ ] Django admin shows "External Platforms" (not "Social Platforms")
- [ ] `ruff check` and `ruff format` pass
