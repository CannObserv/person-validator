# Name Normalization Pipeline

`POST /v1/find` runs the input name through an ordered chain of `Stage` instances before searching the database.

## PipelineResult Fields

| Field | Type | Description |
|---|---|---|
| `original` | `str` | Raw input — never modified by any stage |
| `resolved` | `str` | Primary normalized string; top search variant |
| `variants` | `list[WeightedVariant]` | Alternative search strings with weights (0.0–1.0) |
| `messages` | `list[str]` | Human-readable transformation notes |
| `is_valid_name` | `bool \| None` | Set to `False` by `InputClassification` for non-person inputs; endpoint returns 422 |

**`WeightedVariant`:** frozen dataclass `(name: str, weight: float)`. Final certainty = base DB certainty × variant weight. Endpoint deduplicates by name, keeping highest weight.

## Stage Order (Production Default)

1. **`InputClassification`** — rejects org names (422), strips parenthetical noise, decodes email-format inputs. Must run first to preserve comma/email evidence.
2. **`BasicNormalization`** — lowercase, strip non-alpha chars, collapse whitespace
3. **`NameParsing`** — surname-first reorder via `nameparser.HumanName`, prefix/suffix stripping
4. **`NicknameExpansion`** — bidirectional given-name variants via `nicknames.NickNamer`; weight 0.85
5. **`TitleExtraction`** — surname-only variant when title prefix stripped; weight 0.70

## Stage Contract

- Stages receive a `PipelineResult`, return a modified copy — never mutate incoming result or touch `original`
- Normalizing stages (e.g. `BasicNormalization`) update `resolved` only — do **not** append to `variants`
- Variant-generating stages (e.g. `NicknameExpansion`, `TitleExtraction`) append to `variants`; endpoint includes them in search

## Assembly

Production pipeline built through `StageRegistry` in `src/api/routes/v1.py`. Add a new stage by registering it and updating the ordered name list — no changes to endpoint or matching layer needed.

## Search

`search(conn, variants: list[WeightedVariant])` in `matching.py` executes two batch SQL queries across all variants:
- One `IN` clause for full-name matches
- One OR-expanded clause for (given, surname) pair matches

Final certainty = base certainty × variant weight
- Primary exact match: 1.0
- Other exact match: 0.9
- Primary partial match: 0.8
- Other partial match: 0.7
