# Person Validator

Web service and application to identify and enrich publicly accessible data about persons.

## Quick Start

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run linter
uv run ruff check .
```

See [AGENTS.md](AGENTS.md) for the full set of development commands and
[docs/local-development.md](docs/local-development.md) for local auth header
injection and dev proxy setup.

## Scheduled Jobs

Two systemd timers run background enrichment and property sync:

| Timer unit | Schedule | Command |
|---|---|---|
| `person-validator-enrichment-cron` | Hourly | `run_enrichment_cron` |
| `person-validator-property-sync` | Weekly (Sun 03:00) | `sync_wikidata_properties` |

Install on a fresh deployment:

```bash
sudo cp deploy/person-validator-enrichment-cron.{timer,service} /etc/systemd/system/
sudo cp deploy/person-validator-property-sync.{timer,service} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now person-validator-enrichment-cron.timer
sudo systemctl enable --now person-validator-property-sync.timer
```

See [AGENTS.md — Scheduled Jobs](AGENTS.md#scheduled-jobs-systemd-timers) for operational commands.
