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
├── .env              # Local secrets (git-ignored)
└── README.md
```

## Secrets

- GitHub PAT is stored in `.env` as `GITHUB_TOKEN`.
- `.env` is git-ignored. Never commit secrets.

## Playbooks

See **[PLAYBOOKS.md](PLAYBOOKS.md)** for the canonical list of commands used
during development (running tests, linting, syncing deps, etc.).

## Conventions

- Keep functions and methods small and focused.
- Prefer explicit imports over wildcard imports.
- Write docstrings for public modules, classes, and functions.
- Test file names mirror source file names: `src/foo.py` → `tests/test_foo.py`.
