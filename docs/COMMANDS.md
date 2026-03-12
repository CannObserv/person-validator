# Development Commands

All commands run from project root. `uv run` uses the managed venv automatically.

## Environment Setup

```bash
uv sync
```

## Tests

```bash
uv run pytest                          # full suite
uv run pytest --cov                    # with coverage
uv run pytest tests/api/               # FastAPI tests only
uv run pytest tests/test_<module>.py   # single file
uv run pytest -k "test_name"           # by name
```

## Linting & Formatting

```bash
uv run ruff check .           # lint check
uv run ruff check . --fix     # lint + auto-fix
uv run ruff format .          # format
uv run ruff format . --check  # format check (no changes)
```

## Dependencies

```bash
uv add <package>               # runtime dependency
uv add --group dev <package>   # dev dependency
uv remove <package>            # remove
uv sync                        # sync after manual pyproject.toml edits
```

## FastAPI

```bash
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8001 --reload
```

## Django Management

```bash
# Prefix all django commands with:
DJANGO_SETTINGS_MODULE=src.web.config.settings uv run python -m django <command>

# Common commands:
DJANGO_SETTINGS_MODULE=src.web.config.settings uv run python -m django migrate
DJANGO_SETTINGS_MODULE=src.web.config.settings uv run python -m django makemigrations
DJANGO_SETTINGS_MODULE=src.web.config.settings uv run python -m django collectstatic --noinput
DJANGO_SETTINGS_MODULE=src.web.config.settings uv run python -m django runserver 0.0.0.0:8000
```

See [local-development.md](local-development.md) for auth header injection when running locally.

## GitHub Token

```bash
export $(grep GITHUB_TOKEN env | xargs)
```

## Service Management

> After any code change to API or Web app, **restart the service**. uvicorn/gunicorn do not auto-reload in production.

```bash
# Restart services
sudo systemctl restart person-validator-web
sudo systemctl restart person-validator-api

# Status & logs
sudo systemctl status person-validator-web
sudo systemctl status person-validator-api
journalctl -u person-validator-web -f
journalctl -u person-validator-api -f

# Install/update systemd unit files from repo
sudo cp deploy/person-validator-web.service /etc/systemd/system/
sudo cp deploy/person-validator-api.service /etc/systemd/system/
sudo systemctl daemon-reload
```

## Scheduled Jobs (systemd timers)

```bash
# Install
sudo cp deploy/person-validator-enrichment-cron.{timer,service} /etc/systemd/system/
sudo cp deploy/person-validator-property-sync.{timer,service} /etc/systemd/system/
sudo systemctl daemon-reload

# Enable (survive reboot)
sudo systemctl enable --now person-validator-enrichment-cron.timer
sudo systemctl enable --now person-validator-property-sync.timer

# Status
sudo systemctl list-timers person-validator-*

# Run enrichment cron manually
DJANGO_SETTINGS_MODULE=src.web.config.settings uv run python -m django run_enrichment_cron
DJANGO_SETTINGS_MODULE=src.web.config.settings uv run python -m django run_enrichment_cron --dry-run
```
