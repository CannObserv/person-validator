# Playbooks — Common Development Commands

All commands assume you are in the project root (`person-validator/`).

## Environment Setup

```bash
# Create / sync the virtual environment and install all dependencies
uv sync
```

## Running Tests

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

## Linting & Formatting

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

## Dependency Management

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

## GitHub (requires GITHUB_TOKEN in .env)

```bash
# Source the token into your shell
export $(grep GITHUB_TOKEN .env | xargs)
```
