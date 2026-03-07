# Person Validator — Agent Guidelines

## Project Overview

Person Validator is a web service and application that identifies and enriches
publicly accessible data about persons.

## Development Methodology

This is a **red/green TDD** project. All feature and fix work follows this cycle:

1. **Red** — Write a failing test that describes the desired behavior.
2. **Green** — Write the minimum production code to make the test pass.
3. **Refactor** — Clean up while keeping tests green.

No production code is written without a corresponding test first.

## Environment & Tooling

- **Python ≥ 3.12**
- **uv** for environment creation, dependency management, and script execution.
- **pytest** as the test runner.
- **ruff** for linting and formatting.

## Project Layout

```
person-validator/
├── src/
│   ├── api/                  # FastAPI application
│   │   ├── asgi.py           # ASGI entrypoint (uvicorn src.api.asgi:app)
│   │   ├── main.py           # App factory (create_app)
│   │   ├── auth.py           # API key dependency (X-API-Key header)
│   │   ├── db.py             # SQLite connection management (DATABASE_PATH env var)
│   │   ├── schemas.py        # Shared Pydantic models
│   │   └── routes/           # Versioned route modules
│   │       ├── __init__.py   # Re-exports routers
│   │       ├── health.py     # Public /health endpoint
│   │       └── v1.py         # Authenticated /v1/ endpoints
│   ├── core/                 # Shared domain logic (fields, utilities)
│   │   ├── fields.py         # ULIDField
│   │   ├── key_validation.py # Single-sourced API key validation (raw SQL)
│   │   ├── matching.py       # Name search (raw SQL); search(conn, variants) batch query
│   │   ├── pipeline/         # Name normalization pipeline framework
│   │   │   ├── __init__.py   # Public re-exports (Pipeline, Stage, PipelineResult, …)
│   │   │   ├── base.py       # PipelineResult dataclass, Stage ABC, Pipeline runner
│   │   │   ├── registry.py   # StageRegistry — config-driven pipeline assembly
│   │   │   └── stages.py     # Concrete stages (BasicNormalization)
│   │   └── enrichment/       # Enrichment provider framework
│   │       ├── __init__.py   # Public re-exports (all types, Provider, EnrichmentRunner, run_enrichment_for_person, …)
│   │       ├── attribute_types.py  # Pydantic discriminated union; VALUE_TYPE_CHOICES, LABELABLE_TYPES
│   │       ├── base.py       # Provider ABC (dependencies, output_keys, can_run, refresh_interval, required_platforms), Dependency, CircularDependencyError, NoMatchSignal, PersonData, EnrichmentResult, EnrichmentRunResult
│   │       ├── name_utils.py # infer_name_type — name type heuristic for provider-created names
│   │       ├── registry.py   # ProviderRegistry — register/enable/disable providers
│   │       ├── runner.py     # EnrichmentRunner — dependency graph, topological sort, parallel execution, validate, persist; handles NoMatchSignal; accepts provider_kwargs: dict[str,dict] forwarded to each provider.enrich()
│   │       ├── tasks.py      # run_enrichment_for_person, bump_wikidata_confidence — synchronous task utilities called by signals and admin; builds provider_kwargs for confirmed_wikidata_qid and force_rescore
│   │       └── providers/    # Concrete enrichment provider implementations
│   │           ├── wikimedia_client.py  # WikimediaHttpClient — shared session, retry, Action API + SPARQL + Wikipedia REST API
│   │           ├── wikidata.py          # WikidataProvider — search, disambiguate, auto-link, extract
│   │           └── wikipedia.py         # WikipediaProvider — enwiki sitelink → article URL + plain-text extract
│   └── web/                  # Django application
│       ├── config/           # Settings, urls, wsgi/asgi
│       ├── accounts/         # User model + exe.dev email auth backend
│       ├── persons/          # Person, PersonName, PersonAttribute, AttributeLabel, ExternalPlatform, ExternalIdentifierProperty, WikidataCandidateReview
│       │   ├── review_handlers.py  # DISPATCH table + per-status handlers (handle_accepted, handle_confirmed)
│       │   └── signals.py    # pre_save/post_save for WikidataCandidateReview; wired in PersonsConfig.ready()
│       └── keys/             # API key model & admin management
├── tests/                    # Test suite (mirrors src/ structure)
│   ├── api/                  # FastAPI tests
│   └── web/                  # Django tests
├── pyproject.toml            # Project metadata & tool config
├── deploy/                   # Systemd unit files (version-controlled)
│   ├── person-validator-web.service
│   └── person-validator-api.service
├── AGENTS.md                 # This file — agent conventions
├── skills/                   # Agent skills (agentskills.io spec)
│   ├── reviewing-code-claude/    # Local override
│   ├── shipping-work-claude/     # Local override
│   └── reviewing-architecture-claude -> ../vendor/gregoryfoster-skills/skills/reviewing-architecture-claude
├── vendor/
│   └── gregoryfoster-skills/    # Git submodule: github.com/gregoryfoster/skills
├── env                       # Local secrets (git-ignored)
└── README.md
```

### Pipeline Architecture

`POST /v1/find` runs the input name through an ordered chain of `Stage` instances
before searching the database. Each stage receives a `PipelineResult` and returns
a modified copy — it may update `resolved` (the primary search string) and/or
append additional strings to `variants`.

**Contract:**
- Stages only update `resolved` and `variants` — they never mutate the incoming
  result or touch `original`.
- A stage that only normalises input (e.g. `BasicNormalization`) updates
  `resolved` but does **not** append it to `variants`. The endpoint is responsible
  for placing `resolved` first in the search variant list.
- Stages that generate alternatives (e.g. nickname expansion) append those
  alternatives to `variants`; the endpoint includes them in the search.

**Assembly:** The production default pipeline is built through `StageRegistry`
in `src/api/routes/v1.py`. New stages are added by registering them and updating
the ordered name list — no changes to the endpoint or matching layer required.

**Search:** `search(conn, variants)` in `matching.py` executes two batch SQL
queries across all variants: one `IN` clause for full-name matches, one
OR-expanded clause for (given, surname) pair matches.

---

### Database Tables

| Table | App | Purpose |
|---|---|---|
| `persons_person` | persons | Identity anchor, denormalized primary name |
| `persons_personname` | persons | All name variants for a person |
| `persons_personattribute` | persons | Enrichment data (append-only EAV); `value_type` (indexed) + `metadata` (JSONField) |
| `persons_attributelabel` | persons | Controlled label vocabulary per `value_type` (e.g. "work", "home") |
| `persons_externalplatform` | persons | Controlled platform/identity vocabulary for `platform_url` attributes |
| `persons_externalidentifierproperty` | persons | Wikidata external identifier property taxonomy; used by WikidataProvider to extract and construct URLs; managed by `sync_wikidata_properties` command |
| `persons_enrichmentrun` | persons | Audit log of provider runs (one row per person+provider invocation) |
| `persons_wikidatacandidatereview` | persons | Ambiguous/low-confidence Wikidata search results queued for admin review; post-save signal triggers enrichment on acceptance |
| `keys_apikey` | keys | API key hashes for FastAPI auth |

**`PersonAttribute.value_type` values:** `text`, `email`, `phone`, `url`, `platform_url`, `location`, `date`.
Defined in `src/core/enrichment/attribute_types.VALUE_TYPE_CHOICES` (imported by `models.py`).

**Labelable types** (`metadata["label"]` supported): `email`, `phone`, `url`, `platform_url`, `location`.
Defined in `src/core/enrichment/attribute_types.LABELABLE_TYPES`.

### Services

| Service | Framework | Port | Systemd Unit |
|---|---|---|---|
| Web/Admin | Django | 8000 | `person-validator-web` |
| API | FastAPI | 8001 | `person-validator-api` |

### API Versioning Strategy

**Versioning scheme:** URL prefix only (`/v1/`, `/v2/`, …). No header-based negotiation. Stable versions only — no `/v2beta/` or experimental channels.

**Breaking vs. non-breaking changes:**

A *breaking change* requires a new major version:
- Removing or renaming an endpoint, request field, or response field
- Changing the type or format of a field
- Tightening validation (a previously-accepted value is now rejected)
- Changing field semantics in a way that would silently alter client behavior

A *non-breaking change* may be made within the current version:
- Adding a new optional request or response field
- Adding a new endpoint
- Relaxing validation on existing inputs
- Bug fixes that restore documented behavior

**Deprecation timeline:** When a successor version ships, the prior version enters a **1-month sunset window**, after which it is removed.

**Deprecation signaling (three channels — applied during the sunset window):**
1. `Deprecation: true` and `Sunset: <RFC 1123 date>` HTTP response headers (RFC 8594) on every response from the deprecated version.
2. `deprecation_warning` field in every response body pointing clients to the new version.
3. FastAPI router and endpoints marked `deprecated=True` so notices appear in `/docs` and `/redoc`.

**Version discovery:** `GET /versions` (public, no auth) returns all supported versions with `status` (`"stable"` | `"deprecated"`) and `sunset_date` (ISO 8601, deprecated entries only). The version registry lives in `src/api/routes/health.py` as `_API_VERSIONS`.

---

### API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | None | Public health check |
| GET | `/versions` | None | List supported API versions and deprecation status |
| GET | `/v1/health` | API key | Authenticated health check |
| POST | `/v1/find` | API key | Find persons by name query |
| GET | `/v1/read/{id}` | API key | Full person record by ID |

#### GET /v1/read/{id}

Returns a full person record including all name variants and enrichment
attributes. Returns 200 with `PersonReadResponse` (id, name, given_name,
middle_name, surname, created_at, updated_at, names[], attributes[]) or
404 with `{"message": "Person not found"}`.

#### POST /v1/find

Accepts `{"name": "..."}`. Normalizes input (lowercase, strip non-letters,
collapse whitespace), searches `persons_personname` for exact `full_name`
matches and `given_name`+`surname` combinations. Returns 200 with scored
results or 404 with empty results. Certainty scoring: primary exact = 1.0,
other exact = 0.9, primary partial = 0.8, other partial = 0.7.

## Secrets

- GitHub PAT is stored in `env` as `GITHUB_TOKEN`.
- `env` is git-ignored. Never commit secrets.

## Common Development Commands

All commands assume you are in the project root (`person-validator/`).

### Environment Setup

```bash
# Create / sync the virtual environment and install all dependencies
uv sync
```

### Running Tests

```bash
# Run the full test suite
uv run pytest

# Run tests with coverage report
uv run pytest --cov

# Run a single test file
uv run pytest tests/test_<module>.py

# Run a single test by name
uv run pytest -k "test_name"
```

### Linting & Formatting

```bash
# Lint (check only)
uv run ruff check .

# Lint and auto-fix
uv run ruff check . --fix

# Format
uv run ruff format .

# Format check (no changes)
uv run ruff format . --check
```

### Dependency Management

```bash
# Add a runtime dependency
uv add <package>

# Add a dev dependency
uv add --group dev <package>

# Remove a dependency
uv remove <package>

# Sync lockfile after manual pyproject.toml edits
uv sync
```

### GitHub (requires GITHUB_TOKEN in `env`)

```bash
# Source the token into your shell
export $(grep GITHUB_TOKEN env | xargs)
```

### FastAPI Development

```bash
# Run the FastAPI dev server
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8001 --reload

# Run only FastAPI tests
uv run pytest tests/api/
```

### Django Management

```bash
# Run migrations
DJANGO_SETTINGS_MODULE=src.web.config.settings uv run python -m django migrate

# Create migrations after model changes
DJANGO_SETTINGS_MODULE=src.web.config.settings uv run python -m django makemigrations

# Collect static files
DJANGO_SETTINGS_MODULE=src.web.config.settings uv run python -m django collectstatic --noinput

# Run Django dev server (with exe.dev header injection for local testing)
DJANGO_SETTINGS_MODULE=src.web.config.settings uv run python -m django runserver 0.0.0.0:8000
```

### Service Management

> **After any code change to the API or Web app, restart the corresponding
> service.** The systemd-managed uvicorn/gunicorn processes do not auto-reload
> in production. Forgetting this step means the running service still serves
> the old code.

```bash
# Install/update systemd unit files from repo
sudo cp deploy/person-validator-web.service /etc/systemd/system/
sudo cp deploy/person-validator-api.service /etc/systemd/system/
sudo systemctl daemon-reload

# Start/restart services
sudo systemctl restart person-validator-web
sudo systemctl restart person-validator-api

# Check service status
sudo systemctl status person-validator-web
sudo systemctl status person-validator-api

# View logs
journalctl -u person-validator-web -f
journalctl -u person-validator-api -f
```

## Agent Skills

This project follows the [agentskills.io](https://agentskills.io) spec.
Skills live in the `skills/` directory and are auto-discovered by the agent
framework. A skill is either a **local override** (committed directory) or a
**symlink** to an external skills repo vendored as a git submodule.

### External skill repos (git submodules)

| Repo | Submodule path |
|---|---|
| [`gregoryfoster/skills`](https://github.com/gregoryfoster/skills) | `vendor/gregoryfoster-skills/` |

After cloning this project, initialize submodules:
```bash
git submodule update --init --recursive
```

**At the start of every conversation**, pull the latest upstream skills:
```bash
git submodule update --remote --merge vendor/gregoryfoster-skills
```
If the submodule ref changed, commit it:
```bash
git add vendor/gregoryfoster-skills
git commit -m "chore: update gregoryfoster-skills submodule"
```

To add a new external skill repo, follow the `managing-skills-claude` skill
(available in `vendor/gregoryfoster-skills/skills/managing-skills-claude/`).

### Available skills

| Skill | Source | Triggers |
|---|---|---|
| `reviewing-code-claude` | Local override | CR, code review, perform a review |
| `reviewing-architecture-claude` | Symlink → `vendor/gregoryfoster-skills/` | AR, architecture review, architectural review |
| `shipping-work-claude` | Local override | ship it, push GH, close GH, wrap up |

### Local overrides

A committed directory in `skills/` with the same name as a symlinked global
skill **completely supersedes** the global version (no inheritance). The local
version must be fully self-contained.

| Skill | Override reason |
|---|---|
| `reviewing-code-claude` | Adds `ruff` to gather-context; Django ORM safety, migration safety, pipeline stage contract, TDD discipline, JSON logging, and FastAPI/Pydantic-specific review dimensions |
| `shipping-work-claude` | Concrete `uv run pytest -x` + `uv run ruff check` in `pre-ship.sh`; encodes `#<n> [type]: <desc>` commit convention |

## Conventions

### Logging

All log output is **JSON** (via `python-json-logger`). Both services share a
single `LOG_LEVEL` environment variable (default `INFO`).

**In every module** — obtain a logger at module level, never inside functions:

```python
from src.core.logging import get_logger

logger = get_logger(__name__)
```

**At entry points only** (FastAPI app factory, Django `AppConfig.ready()`,
management commands) — call `configure_logging()` once:

```python
from src.core.logging import configure_logging

configure_logging()  # idempotent; safe to call multiple times
```

Do **not** call `configure_logging()` in library/utility modules.

Django's `LOGGING` dict (in `settings.py`) wires the `django`, `django.request`,
`django.security`, `django.db.backends`, and `src` loggers to the JSON console
handler. FastAPI wires the same via `configure_logging()` in `create_app()`.

### Date & Time

- **All timestamps are stored in UTC.** Django settings enforce `USE_TZ = True`
  and `TIME_ZONE = "UTC"`. Do not change these.
- **Use ISO 8601 format** for all date/time serialization:
  - Timestamps: `YYYY-MM-DDTHH:MM:SS.ffffffZ` (e.g. `2025-01-15T08:30:00.000000Z`)
  - Dates: `YYYY-MM-DD` (e.g. `2025-01-15`)
- In Python, use `django.utils.timezone.now()` for the current time — never
  `datetime.datetime.now()` or `datetime.datetime.utcnow()`.
- When calling `QuerySet.update()`, always include `updated_at=timezone.now()`
  because `.update()` bypasses `auto_now`.

### Commit message convention

When **not** associated with a GitHub issue:
```
[type]: <description>
```

When associated with one or more GitHub issues:
```
#<number> [type]: <description>
```
Multiple issues: `#12, #14 [type]: <description>`

Common types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`.

The `shipping-work-claude` skill follows this convention when auto-committing uncommitted work.

### General

- Keep functions and methods small and focused.
- Prefer explicit imports over wildcard imports.
- **No inline module imports.** All `import` and `from … import` statements
  belong at the top of the file — in both production and test code. Do not
  import inside functions, methods, or test bodies.
- Write docstrings for public modules, classes, and functions.
- Test file names mirror source file names: `src/foo.py` → `tests/test_foo.py`.
  Cross-cutting convention tests (e.g. `test_settings.py`) are the exception.
