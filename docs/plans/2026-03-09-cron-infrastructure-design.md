# Cron Infrastructure + ExternalIdentifierProperty Auto-Sync — Design

> Issues: #28, #33
> Status: Approved

---

## Goal

Ship two scheduled jobs (hourly enrichment cron, weekly property sync) as Django
management commands backed by systemd timer units. Simultaneously address silent
data loss when `ExternalIdentifierProperty` is empty (#33), and surface a clear
operator warning at startup and per-run.

---

## Approved Approach

### 1. `run_enrichment_for_person` — add `provider_names`

Add `provider_names: list[str] | None = None` to the signature in
`src/core/enrichment/tasks.py`. Pass it through to `runner.run()`. All existing
callers omit it and get unchanged behavior.

**Rationale:** The cron is the first caller that needs per-person selective
execution. Extending the existing function is simpler than duplicating its
registry-building and runner-wiring logic in the command.

---

### 2. `run_enrichment_cron` management command

**Location:** `src/web/persons/management/commands/run_enrichment_cron.py`

#### Startup check (integrates #33)

Before the main loop, check:
```python
if ExternalIdentifierProperty.objects.filter(is_enabled=True).count() == 0:
    call_command("sync_wikidata_properties")
```
The 24h guard in `sync_wikidata_properties` allows this through naturally: on a
fresh deployment `last_synced_at` is `None`, so the guard condition
(`last_synced_at IS NOT NULL AND age < 24h`) is false. No bypass flag needed.

#### Main loop — per-Person approach

```
For each Person in batches of 50:
    stale_providers = [P for P in registered_providers if is_stale(person, P)]
    if "wikidata" in stale_providers and person has a rejected WikidataCandidateReview:
        remove "wikidata" from stale_providers
    if stale_providers is empty:
        continue
    run_enrichment_for_person(
        person_id=person.pk,
        triggered_by="cron",
        provider_names=[p.name for p in stale_providers],
    )
```

**Rationale for per-Person (not per-Provider):** Runs the full dependency-aware
`EnrichmentRunner` once per person rather than once per provider×person. The
runner's topological sort correctly sequences dependencies (e.g. Wikidata before
Wikipedia) within a single call. This avoids N×M runner invocations and matches
how all other callers work.

#### Staleness determination

Per-person query — one DB hit per person:
```python
EnrichmentRun.objects
    .filter(person=person, provider__in=provider_names)
    .values("provider")
    .annotate(latest=Max("started_at"), latest_status=...)
```
A provider is stale for a person if:
- No `EnrichmentRun` row exists for that person+provider, **or**
- Most recent run has `status="failed"`, **or**
- `latest < now - provider.refresh_interval`

#### Command options

| Flag | Behaviour |
|---|---|
| `--dry-run` | Print what would run; no enrichment executed |
| `--provider NAME` | Limit to one provider (still per-person loop) |
| `--person-id ID` | Enrich one person, bypass staleness check, run all providers |
| `--limit N` | Cap total persons processed (useful for testing) |

#### Exit codes

- `0` — success (per-person failures are logged, not fatal)
- `1` — fatal configuration error (DB unreachable, etc.)

---

### 3. `sync_wikidata_properties` additions

Two additions to the existing command:

**`--dry-run` flag:** Fetches all SPARQL pages and reports created/updated/skipped
counts but writes no DB rows.

**24h guard:** At the top of `handle()`:
```python
last_run = ExternalIdentifierProperty.objects.aggregate(Max("last_synced_at"))["last_synced_at__max"]
if last_run and (now - last_run) < timedelta(hours=24):
    logger.info("sync_wikidata_properties: last sync was %s ago — skipping", ...)
    return
```
Prevents runaway re-sync if the timer fires unexpectedly often. Skipped silently
(INFO log) rather than with an error.

---

### 4. Issue #33 — Operator warnings

**`WikidataProvider.enrich()`:** If `ExternalIdentifierProperty.objects.filter(is_enabled=True).count() == 0`, emit a structured `WARNING` log and skip only the external-ID extraction block. The provider still writes `wikidata_qid`, `wikidata_label`, Wikipedia sitelink, and aliases — only the `platform_url` attributes derived from external identifier properties are skipped.

```python
logger.warning(
    "ExternalIdentifierProperty table is empty; external ID extraction skipped. "
    "Run: manage.py sync_wikidata_properties",
)
```

**`PersonsConfig.ready()`:** Query the table on app startup. If empty:
```python
logger.warning(
    "ExternalIdentifierProperty table is empty. "
    "Wikidata external ID extraction will be skipped until you run: "
    "manage.py sync_wikidata_properties"
)
```

---

### 5. Systemd units

Four new files in `deploy/`:

**`person-validator-enrichment-cron.timer`** — fires hourly, 5 min after boot:
```ini
[Unit]
Description=Person Validator — hourly enrichment cron

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

**`person-validator-enrichment-cron.service`** — oneshot; invokes the command:
```ini
[Unit]
Description=Person Validator — enrichment cron run
After=network-online.target

[Service]
Type=oneshot
User=exedev
WorkingDirectory=/home/exedev/person-validator
EnvironmentFile=/home/exedev/person-validator/env
ExecStart=/home/exedev/person-validator/.venv/bin/python -m django \
    run_enrichment_cron --settings src.web.config.settings
StandardOutput=journal
StandardError=journal
```

**`person-validator-property-sync.timer`** — fires weekly on Sunday at 03:00:
```ini
[Unit]
Description=Person Validator — weekly Wikidata property sync

[Timer]
OnCalendar=Sun 03:00
Persistent=true

[Install]
WantedBy=timers.target
```

**`person-validator-property-sync.service`** — same pattern, command = `sync_wikidata_properties`.

---

### 6. Documentation

**`README.md`** — add a "Scheduled Jobs" subsection to the existing Service
Management section covering both timers:
```bash
sudo cp deploy/person-validator-enrichment-cron.{timer,service} /etc/systemd/system/
sudo cp deploy/person-validator-property-sync.{timer,service} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now person-validator-enrichment-cron.timer
sudo systemctl enable --now person-validator-property-sync.timer
```

**`AGENTS.md`** — extend the Services table with the two new timers and add the
management commands to the Common Development Commands section.

---

## Key Decisions

| Decision | Rationale |
|---|---|
| Per-Person cron loop | Aligns with existing `run_enrichment_for_person` architecture; runner's dependency graph handles ordering |
| 24h guard uses `Max(last_synced_at)` | Table-wide max is a single cheap aggregate; naturally `None` on first run, bypassing the guard |
| Empty-table path triggers sync before cron loop | First-run UX: operator deploys and runs cron; enrichment proceeds without manual intervention |
| `WikidataProvider` skips only external-ID extraction, not full run | Core Wikidata data (QID, label, aliases, Wikipedia sitelink) is still written; only `platform_url` attributes sourced from `ExternalIdentifierProperty` are skipped |
| `AppConfig.ready()` warning (not system check) | Fires on every startup including gunicorn/uvicorn; ensures operators see it in service logs |

---

## Out of Scope

- Async task queue / Celery (no task queue exists; cron is synchronous oneshot)
- Wikimedia EventStream (Phase 2, deferred until corpus exists — see design doc)
- Per-provider concurrency limits
- VIAF, ORCID, OpenSecrets providers (not yet implemented; cron will enrich with whatever providers are registered at call time)
