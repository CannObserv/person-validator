# Enhanced Normalization Pipeline Design

**Date:** 2026-03-10
**Status:** Approved

## Goal

Extend the `/v1/find` pipeline to:

1. Clean and normalize malformed name inputs before searching
2. Generate weighted name variants to improve match recall
3. Classify inputs that are clearly not person names and reject them with a 422

All changes are contained within the existing `/v1/find` flow — no new endpoints.

---

## Approved Approach

### `WeightedVariant` and `PipelineResult` changes

Add a `WeightedVariant` dataclass to `src/core/pipeline/base.py`:

```python
@dataclass(frozen=True)
class WeightedVariant:
    name: str
    weight: float  # certainty multiplier; 1.0 = full confidence
```

Extend `PipelineResult`:

```python
@dataclass
class PipelineResult:
    original: str
    resolved: str
    variants: list[WeightedVariant]   # was list[str]
    messages: list[str]               # soft warnings surfaced in response
    is_valid_name: bool | None = None # None = not yet assessed
```

`resolved` always carries implicit weight 1.0. Stages append `WeightedVariant`
instances to `variants`. Deduplication in the endpoint keeps the highest weight
when two stages produce the same string.

### Matching layer

`search()` in `matching.py` accepts `list[WeightedVariant]`. Final certainty is
`base_certainty × variant.weight`, where base certainty uses the existing
DB-driven scale:

| Match type | Base certainty |
|---|---|
| Exact `full_name`, `is_primary` | 1.0 |
| Exact `full_name`, not primary | 0.9 |
| `given_name` + `surname` pair, `is_primary` | 0.8 |
| `given_name` + `surname` pair, not primary | 0.7 |

The endpoint prepends `WeightedVariant(name=resolved, weight=1.0)` and
deduplicates by `.name` before calling `search()`.

`QueryInfo.variants` in the API response stays `list[str]` — the endpoint
extracts `.name` from each `WeightedVariant`. Weights are internal.

### API schema changes

`FindResponse.message: str | None` → `messages: list[str]` (in-place; treated
as non-breaking by project decision given current distribution state).

The endpoint:
- Populates `messages` from `PipelineResult.messages`
- Appends `"No matching persons found"` when results are empty
- Raises `HTTPException(status_code=422, detail={"messages": pipeline_result.messages})`
  when `PipelineResult.is_valid_name is False`, before running the DB search

### Pipeline stage order

```
BasicNormalization → InputClassification → NameParsing → NicknameExpansion → TitleExtraction
```

---

## New Stages

### 1. `InputClassification`

Operates on `original` (before normalization strips evidence). Clean-first
approach — hard rejection is reserved for org suffixes only.

**Hard reject** (sets `is_valid_name=False`):
- Input ends with known organization suffixes: LLC, Corp, Inc, Ltd, Foundation,
  Association, Committee, PAC, Institute, University, College, etc.

**Clean and continue** (updates `resolved`, adds to `messages`):
- Strip parenthesized content: `"John Smith (DUPLICATE)"` → `"John Smith"`,
  message: `"Parenthesized content removed: (DUPLICATE)"`
- Strip digits: `"John Smith 2"` → `"John Smith"`,
  message: `"Digits removed from input"`
- Decode email patterns: `"john.smith@example.com"` → `"John Smith"`,
  message: `"Name extracted from email address"`; only `firstname.lastname@...`
  patterns are decoded — opaque addresses (e.g., `jsmith123@...`) are not

**Reject after cleaning** (sets `is_valid_name=False`):
- Cleaned string is empty
- Cleaned string reduces to a single token that is not plausibly a surname
  (e.g., a pure org keyword)

**Library:** pure heuristics, no external dependency.

---

### 2. `NameParsing`

Uses the [`nameparser`](https://pypi.org/project/nameparser/) PyPI package.

- Detects surname-first ordering (`"Heck, Denny"`) and reorders to
  `"Denny Heck"`; adds message: `"Surname-first format detected and corrected"`
- Strips honorifics and occupational prefixes (`"Mr."`, `"Dr."`, `"Lt. Governor"`)
  and suffixes (`"Jr."`, `"III"`) from `resolved`
- Weight on `resolved`: 1.0 (reordering/stripping does not reduce confidence)

---

### 3. `NicknameExpansion`

Uses the [`nicknames`](https://pypi.org/project/nicknames/) PyPI package.

- Extracts the given name from the parsed result
- Looks up formal ↔ informal variants (`"Denny"` → `"Dennis"`, `"Dennis"` → `"Denny"`)
- Appends each as `WeightedVariant(name=..., weight=0.85)`

---

### 4. `TitleExtraction`

Pure heuristics against a curated title word list.

- Detects occupational title patterns at the start of the input:
  `"Lieutenant Governor Heck"`, `"Senator Smith"`, `"Representative Jones"`
- Extracts the trailing token(s) as a surname-only search variant
- Appends as `WeightedVariant(name=surname, weight=0.70)`

---

## Key Decisions

| Decision | Rationale |
|---|---|
| `WeightedVariant` replaces `list[str]` in `PipelineResult` | Makes stage intent explicit; keeps certainty scores honest |
| Weights multiply base certainty from DB match | Composes the two independent signals cleanly |
| Weights are internal; API exposes only strings | API consumers don't need pipeline internals |
| `InputClassification` cleans before rejecting | Maximizes salvageable inputs; hard-gates only the unambiguous cases |
| `message` → `messages` treated as non-breaking | Current API distribution does not warrant a v2 bump |

## Out of Scope

- **Initials expansion** (`"DLH"` → `"Dennis Lynn Heck"`): requires enrichment
  data (legal name) not available to the pipeline at query time
- **Cultural surname-first detection without comma**: ambiguous without a
  training corpus; deferred
- **NER / ML-based classification**: overkill for single-string input; heuristics
  are sufficient and auditable
- **New API version**: `message` → `messages` change handled in-place
