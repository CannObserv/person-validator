## Context

`PersonName` records currently have a `source` CharField but no structured provenance or confidence scoring. The enrichment system will create `PersonName` records (e.g. Wikidata aliases) and must document *how certain* the name association is and *exactly where it came from* in a machine-readable way. This is required before any provider can write name records.

## Changes to `PersonName`

Add two fields to `src/web/persons/models.py` on the `PersonName` model:

```python
confidence = models.FloatField(
    validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    null=True,
    blank=True,
    help_text="Certainty score [0.0–1.0] for this name record. Null = unscored (e.g. manually entered).",
)
provenance = models.JSONField(
    null=True,
    blank=True,
    help_text=(
        "Structured provenance metadata. Schema is provider-dependent. "
        "Common keys: provider (str), retrieved_at (ISO 8601 str), "
        "source_url (str), wikidata_qid (str), wikidata_alias_lang (str)."
    ),
)
```

### Example provenance payloads

**Wikidata alias:**
```json
{
    "provider": "wikidata",
    "retrieved_at": "2025-07-10T14:00:00Z",
    "wikidata_qid": "Q23",
    "wikidata_alias_lang": "en",
    "source_url": "https://www.wikidata.org/wiki/Q23"
}
```

**VIAF name form:**
```json
{
    "provider": "viaf",
    "retrieved_at": "2025-07-10T14:00:00Z",
    "viaf_id": "31996712",
    "contributing_library": "LC",
    "source_url": "https://viaf.org/viaf/31996712/"
}
```

**Manually entered (no provenance):**
Both `confidence` and `provenance` are `null`.

## Name type inference rules (for provider-created names)

When a provider creates a `PersonName` record and the name type is not explicitly known, the following heuristics apply. These rules are implemented as a utility function `infer_name_type(full_name: str, person: PersonData) -> str` in `src/core/enrichment/name_utils.py`:

1. Default: `"alias"`
2. If the name contains only non-Latin characters (Unicode blocks: Arabic, CJK, Cyrillic, Devanagari, etc.) and the person's primary name is Latin-script → `"transliteration"`
3. If the name is ≤6 characters, all-caps or period-separated initials (e.g. "J.F.K.") → `"abbreviation"`

These heuristics must be conservative. When in doubt, use `"alias"`. The rules are documented in the function docstring.

## Migration

Standard `makemigrations` migration. Both fields are nullable so no default is needed and there is no data migration.

## Acceptance criteria

- [ ] `PersonName.confidence` field exists (FloatField, nullable, validated 0.0–1.0)
- [ ] `PersonName.provenance` field exists (JSONField, nullable)
- [ ] `infer_name_type()` utility exists in `src/core/enrichment/name_utils.py` with tests
- [ ] Existing `PersonName` records are unaffected (both fields null by default)
- [ ] Django admin for `PersonName` shows `confidence` and `provenance`
- [ ] Migration applies cleanly
- [ ] All existing tests pass
