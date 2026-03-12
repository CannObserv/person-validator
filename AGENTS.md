# Person Validator — Agent Guidelines

## Agent Output Style

Be terse. Prefer fragments over full sentences. Skip filler and preamble. Sacrifice grammar for density. Lead with the answer or action. Reserve prose for decisions that need user input, blockers, and natural milestones. No trailing summaries.

## Project Overview

Web service + admin app: identifies and enriches publicly accessible data on persons.

## Development Methodology

TDD required. Red → Green → Refactor. No production code without a failing test first.

## Environment & Tooling

- Python ≥ 3.12, **uv**, **pytest**, **ruff**

## Project Layout

```
src/api/       # FastAPI app (ASGI, routes, auth, schemas)
src/core/      # Shared domain: pipeline/, enrichment/, matching, fields
src/web/       # Django app (persons, accounts, keys, config)
tests/         # Mirrors src/ structure
deploy/        # Systemd unit files
docs/          # Reference docs (API, SCHEMA, PIPELINE, COMMANDS, SKILLS)
```

## Pipeline

Stage order: `InputClassification` → `BasicNormalization` → `NameParsing` → `NicknameExpansion` → `TitleExtraction`

Contracts:
- Stages receive `PipelineResult`, return modified copy — never mutate `original`
- Normalizing stages update `resolved` only — do not append to `variants`
- Variant-generating stages append to `variants`; endpoint includes them in search
- New stages: register in `StageRegistry`, add to ordered list in `src/api/routes/v1.py`

See `docs/PIPELINE.md` for `PipelineResult` fields, `WeightedVariant`, and search query details.

## Services

| Service | Framework | Port | Systemd Unit |
|---|---|---|---|
| Web/Admin | Django | 8000 | `person-validator-web` |
| API | FastAPI | 8001 | `person-validator-api` |
| Enrichment cron | Django mgmt cmd | — | `person-validator-enrichment-cron` (timer) |
| Wikidata property sync | Django mgmt cmd | — | `person-validator-property-sync` (timer) |

**After any code change, restart the service.** uvicorn/gunicorn do not auto-reload in production.

## API

See `docs/API.md` for endpoints, response shapes, versioning policy, and deprecation signaling.

## Database / Schema

See `docs/SCHEMA.md` for table reference, `value_type` values, labelable types, and attribute key conventions.

## Secrets

`env` (git-ignored): `GITHUB_TOKEN`. Never commit secrets.

## Common Development Commands

Non-obvious commands. Full reference: `docs/COMMANDS.md`.

```bash
# Django management prefix
DJANGO_SETTINGS_MODULE=src.web.config.settings uv run python -m django <command>

# FastAPI dev server
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8001 --reload

# GitHub token
export $(grep GITHUB_TOKEN env | xargs)
```

## Agent Skills

Skills in `skills/` (agentskills.io) and `.claude/skills/` (Claude Code). When adding a skill: create both entries. See `docs/SKILLS.md` for layout, submodule management, and authoring.

## Conventions

### Commit Messages

```
#<number> [type]: <description>   # with GitHub issue
[type]: <description>             # without issue
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`. Multiple issues: `#12, #14 [type]: <desc>`

### Logging

```python
from src.core.logging import get_logger
logger = get_logger(__name__)  # module level, never inside functions
```

Entry points only (app factory, `AppConfig.ready()`, management commands): call `configure_logging()` once.

### Date & Time

- All timestamps UTC. `USE_TZ = True`, `TIME_ZONE = "UTC"` — do not change.
- Use `django.utils.timezone.now()` — never `datetime.now()` or `datetime.utcnow()`.
- `QuerySet.update()` bypasses `auto_now` — always include `updated_at=timezone.now()`.
- ISO 8601: timestamps `YYYY-MM-DDTHH:MM:SS.ffffffZ`, dates `YYYY-MM-DD`.

### General

- No inline module imports. All imports at top of file — production and test code.
- Docstrings for public modules, classes, functions.
- Test files mirror source: `src/foo.py` → `tests/test_foo.py`.
- Explicit imports, not wildcard.
- Keep functions small and focused.
