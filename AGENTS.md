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
├── src/              # Application source code
├── tests/            # Test suite (mirrors src/ structure)
├── pyproject.toml    # Project metadata & tool config
├── AGENTS.md         # This file — agent conventions
├── PLAYBOOKS.md      # Frequently-used development commands
├── env               # Local secrets (git-ignored)
└── README.md
```

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

```bash
# Start/restart the Django web service
sudo systemctl restart person-validator-web

# Check service status
sudo systemctl status person-validator-web

# View logs
journalctl -u person-validator-web -f
```

## Playbooks

When the user references a playbook by name or trigger phrase (e.g., `CR`, `ship it`), read **[PLAYBOOKS.md](PLAYBOOKS.md)** and execute the matching procedure. Playbooks define the expected steps, output format, and interaction protocol.

**Resolution order** (most specific wins):
1. **Project-level** — `PLAYBOOKS.md` in the project root
2. **Global** — `~/.config/shelley/PLAYBOOKS.md` (cross-project defaults)

If a playbook name exists in both files, the project-level definition takes precedence. If a playbook exists only in the global file, use it.

## Conventions

- Keep functions and methods small and focused.
- Prefer explicit imports over wildcard imports.
- **No inline module imports.** All `import` and `from … import` statements
  belong at the top of the file — in both production and test code. Do not
  import inside functions, methods, or test bodies.
- Write docstrings for public modules, classes, and functions.
- Test file names mirror source file names: `src/foo.py` → `tests/test_foo.py`.
