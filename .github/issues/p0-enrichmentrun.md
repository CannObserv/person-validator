## Context

The enrichment system needs a persistent audit log of every provider run, per person. This log serves three purposes:

1. **Cron scheduling**: the hourly cron job consults `EnrichmentRun` to decide whether a person/provider pair is due for re-enrichment (based on the provider's `refresh_interval`)
2. **Debugging**: operators can see exactly what each provider returned, when, and what warnings were raised
3. **Trigger attribution**: each run records what initiated it (`cron`, `adjudication`, `manual`, `api`)

## Model

Add to `src/web/persons/models.py`:

```python
class EnrichmentRun(models.Model):
    STATUS_CHOICES = [
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),      # dependency attribute was absent
        ("no_match", "No Match"),    # provider ran but found no matching record
    ]

    TRIGGERED_BY_CHOICES = [
        ("cron", "Cron"),
        ("adjudication", "Adjudication"),
        ("manual", "Manual"),
        ("api", "API"),
    ]

    id = ULIDField(primary_key=True)
    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="enrichment_runs"
    )
    provider = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    attributes_saved = models.PositiveIntegerField(default=0)
    attributes_skipped = models.PositiveIntegerField(default=0)
    warnings = models.JSONField(default=list)
    error = models.TextField(blank=True)
    triggered_by = models.CharField(
        max_length=20, choices=TRIGGERED_BY_CHOICES, blank=True
    )
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "persons_enrichmentrun"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["person", "provider", "-started_at"]),
            models.Index(fields=["provider", "status", "-started_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.provider} / {self.person} / {self.status}"
```

## Runner integration

`EnrichmentRunner.run()` must be updated to create and update `EnrichmentRun` records. Pattern:

```python
run = EnrichmentRun.objects.create(
    person_id=person.id,
    provider=provider.name,
    status="running",
    triggered_by=triggered_by,
    started_at=timezone.now(),
)
try:
    results = provider.enrich(person)
    # ... persist attributes ...
    run.status = "completed"
    run.attributes_saved = ...
    run.attributes_skipped = ...
    run.warnings = [w.__dict__ for w in warnings]
except Exception as exc:
    run.status = "failed"
    run.error = str(exc)
finally:
    run.completed_at = timezone.now()
    run.save()
```

The `triggered_by` value is passed into `EnrichmentRunner.run()` as a parameter (default `"manual"`).

## Django admin

Register `EnrichmentRun` in admin:
- `list_display`: `person`, `provider`, `status`, `attributes_saved`, `attributes_skipped`, `triggered_by`, `started_at`, `completed_at`
- `list_filter`: `provider`, `status`, `triggered_by`
- `search_fields`: `person__name`, `provider`
- Read-only: all fields (append-only log; no editing)

## Acceptance criteria

- [ ] `EnrichmentRun` model exists with all fields above
- [ ] DB table is `persons_enrichmentrun` with both indexes
- [ ] `EnrichmentRunner.run()` creates/updates `EnrichmentRun` records
- [ ] `triggered_by` parameter plumbed through runner
- [ ] Django admin lists runs with filtering and search
- [ ] All fields are read-only in admin
- [ ] All existing tests pass; new tests cover run record creation for success/failure/skipped cases
