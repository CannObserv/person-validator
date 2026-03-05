## Context

The enrichment system needs two scheduled jobs:
1. **Hourly enrichment cron**: re-enriches persons whose provider runs are stale (older than `provider.refresh_interval`)
2. **Weekly property sync**: refreshes `ExternalIdentifierProperty` records from Wikidata SPARQL

Both are Django management commands invoked by systemd timer units.

## Management command: `run_enrichment_cron`

Location: `src/web/persons/management/commands/run_enrichment_cron.py`

### Logic

```
For each enabled provider P (in topological order):
  stale_persons = persons whose most recent EnrichmentRun for P is either:
    - absent (never run)
    - older than now - P.refresh_interval
    - status = "failed" (retry)
  For each stale person:
    Load PersonData (name, attributes)
    Run EnrichmentRunner with provider_names=[P.name], triggered_by="cron"
```

Process persons in batches of 50 to avoid memory pressure. Log progress at INFO level.

**Do NOT re-run providers for persons with a `WikidataCandidateReview` in `status="rejected"` for the Wikidata provider** — the admin has confirmed there is no match.

### Command options

```
--dry-run     Print what would run without executing
--provider    Limit to a specific provider name
--person-id   Enrich a single person (ignores staleness check)
--limit N     Cap total persons processed (useful for testing)
```

### Exit codes

- 0: success (even if some persons failed — failures are logged)
- 1: fatal configuration error (missing API key, DB unreachable)

## Management command: `sync_wikidata_properties`

Already specified in the `ExternalIdentifierProperty` issue. This issue adds:
- A `--dry-run` flag
- Logging of created/updated/skipped counts at INFO level
- An hourly check: if last sync was within 24 hours, skip (guard against runaway cron)

## Systemd timer units

### Hourly enrichment timer

`deploy/person-validator-enrichment-cron.timer`:
```ini
[Unit]
Description=Person Validator — hourly enrichment cron
After=person-validator-api.service

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

`deploy/person-validator-enrichment-cron.service`:
```ini
[Unit]
Description=Person Validator — enrichment cron run
After=network-online.target

[Service]
Type=oneshot
User=exedev
WorkingDirectory=/home/exedev/person-validator
EnvironmentFile=/home/exedev/person-validator/env
ExecStart=/home/exedev/person-validator/.venv/bin/python -m django run_enrichment_cron
  --settings src.web.config.settings
StandardOutput=journal
StandardError=journal
```

### Weekly property sync timer

`deploy/person-validator-property-sync.timer`:
```ini
[Unit]
Description=Person Validator — weekly Wikidata property sync

[Timer]
OnCalendar=Sun 03:00
Persistent=true

[Install]
WantedBy=timers.target
```

`deploy/person-validator-property-sync.service`: same pattern as above, command = `sync_wikidata_properties`.

### Installation instructions

Add to PLAYBOOKS.md and README:
```bash
sudo cp deploy/person-validator-enrichment-cron.{timer,service} /etc/systemd/system/
sudo cp deploy/person-validator-property-sync.{timer,service} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now person-validator-enrichment-cron.timer
sudo systemctl enable --now person-validator-property-sync.timer
```

## Acceptance criteria

- [ ] `run_enrichment_cron` management command with all options
- [ ] Skips rejected-review persons for Wikidata provider
- [ ] Batched processing (50 per batch)
- [ ] `--dry-run`, `--provider`, `--person-id`, `--limit` flags work
- [ ] `sync_wikidata_properties` `--dry-run` flag added; 24h guard added
- [ ] Both timer and service unit files in `deploy/`
- [ ] Installation instructions in README
- [ ] Tests cover: staleness logic, dry-run, rejected-review skip
