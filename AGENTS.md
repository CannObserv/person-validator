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
│   │       ├── __init__.py   # Public re-exports (all types, Provider, EnrichmentRunner, …)
│   │       ├── attribute_types.py  # Pydantic discriminated union; VALUE_TYPE_CHOICES, LABELABLE_TYPES
│   │       ├── base.py       # Provider ABC, EnrichmentResult, EnrichmentWarning, EnrichmentRunResult
│   │       ├── registry.py   # ProviderRegistry — register/enable/disable providers
│   │       └── runner.py     # EnrichmentRunner — validate, strip labels/platforms, persist
│   └── web/                  # Django application
│       ├── config/           # Settings, urls, wsgi/asgi
│       ├── accounts/         # User model + exe.dev email auth backend
│       ├── persons/          # Person, PersonName, PersonAttribute, AttributeLabel, SocialPlatform
│       └── keys/             # API key model & admin management
├── tests/                    # Test suite (mirrors src/ structure)
│   ├── api/                  # FastAPI tests
│   └── web/                  # Django tests
├── pyproject.toml            # Project metadata & tool config
├── deploy/                   # Systemd unit files (version-controlled)
│   ├── person-validator-web.service
│   └── person-validator-api.service
├── AGENTS.md                 # This file — agent conventions
├── PLAYBOOKS.md              # Frequently-used development commands
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
| `persons_socialplatform` | persons | Controlled platform vocabulary for `platform_url` attributes |
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

### API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | None | Public health check |
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

## Playbooks

When the user references a playbook by name or trigger phrase (e.g., `CR`, `ship it`), read **[PLAYBOOKS.md](PLAYBOOKS.md)** and execute the matching procedure. Playbooks define the expected steps, output format, and interaction protocol.

**Resolution order** (most specific wins):
1. **Project-level** — `PLAYBOOKS.md` in the project root
2. **Global** — `~/.config/shelley/PLAYBOOKS.md` (cross-project defaults)

If a playbook name exists in both files, the project-level definition takes precedence. If a playbook exists only in the global file, use it.

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

### General

- Keep functions and methods small and focused.
- Prefer explicit imports over wildcard imports.
- **No inline module imports.** All `import` and `from … import` statements
  belong at the top of the file — in both production and test code. Do not
  import inside functions, methods, or test bodies.
- Write docstrings for public modules, classes, and functions.
- Test file names mirror source file names: `src/foo.py` → `tests/test_foo.py`.
  Cross-cutting convention tests (e.g. `test_settings.py`) are the exception.
