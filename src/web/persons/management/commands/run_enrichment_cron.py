"""Management command: run_enrichment_cron.

Iterates over all persons and re-enriches those with at least one stale
provider (no prior run, failed run, or run older than provider.refresh_interval).

Optionally triggers sync_wikidata_properties first if ExternalIdentifierProperty
is empty (fresh deployment guard).
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from src.core.enrichment.tasks import _build_default_registry, run_enrichment_for_person
from src.core.logging import configure_logging, get_logger

logger = get_logger(__name__)

BATCH_SIZE = 50


def _prefetch_runs_for_batch(batch, providers) -> dict:
    """Return {person_pk: {provider_name: latest_run_dict}} for all persons in *batch*.

    Single DB query replaces per-person EnrichmentRun lookups in the main loop.
    """
    from src.web.persons.models import EnrichmentRun  # noqa: PLC0415

    provider_names = [p.name for p in providers]
    all_runs = list(
        EnrichmentRun.objects.filter(person__in=batch, provider__in=provider_names)
        .values("person_id", "provider", "started_at", "status")
        .order_by("provider", "-started_at")
    )
    runs_by_person: dict = {}
    for run in all_runs:
        pid = run["person_id"]
        pname = run["provider"]
        runs_by_person.setdefault(pid, {})
        if pname not in runs_by_person[pid]:
            runs_by_person[pid][pname] = run
    return runs_by_person


def _prefetch_rejected_person_ids(batch) -> set:
    """Return the set of person PKs in *batch* with a rejected WikidataCandidateReview."""
    from src.web.persons.models import WikidataCandidateReview  # noqa: PLC0415

    return set(
        WikidataCandidateReview.objects.filter(person__in=batch, status="rejected")
        .values_list("person_id", flat=True)
    )


def _stale_provider_names(person_pk, providers, runs_by_person: dict, now) -> list[str]:
    """Return names of providers that are stale for *person_pk*.

    A provider is stale when:
    - No EnrichmentRun exists for this person + provider, OR
    - Most recent run has status='failed', OR
    - Most recent run started_at < now - provider.refresh_interval

    *runs_by_person* and *now* are pre-computed per batch to avoid per-person queries.
    """
    latest_run = runs_by_person.get(person_pk, {})
    stale = []
    for provider in providers:
        run = latest_run.get(provider.name)
        if run is None:
            stale.append(provider.name)
        elif run["status"] == "failed":
            stale.append(provider.name)
        elif run["started_at"] < now - provider.refresh_interval:
            stale.append(provider.name)
    return stale


class Command(BaseCommand):
    """Re-enrich persons whose provider runs are stale."""

    help = (
        "Re-enrich persons with stale provider data. "
        "Triggers sync_wikidata_properties first if ExternalIdentifierProperty is empty."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print what would run without executing enrichment.",
        )
        parser.add_argument(
            "--provider",
            default=None,
            help="Limit enrichment to a single provider name.",
        )
        parser.add_argument(
            "--person-id",
            default=None,
            help="Enrich a single person by ID, bypassing staleness check.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Cap total persons processed.",
        )

    def handle(self, *args, **options):
        configure_logging()
        dry_run = options["dry_run"]
        provider_filter = options["provider"]
        person_id = options["person_id"]
        limit = options["limit"]

        # ----------------------------------------------------------------
        # Auto-sync: trigger property sync on empty table (fresh deploy)
        # ----------------------------------------------------------------
        from src.web.persons.models import ExternalIdentifierProperty  # noqa: PLC0415

        if not dry_run and not ExternalIdentifierProperty.objects.filter(is_enabled=True).exists():
            logger.info(
                "run_enrichment_cron: ExternalIdentifierProperty table is empty — "
                "triggering sync_wikidata_properties first",
            )
            call_command("sync_wikidata_properties")

        # ----------------------------------------------------------------
        # Build provider list (filter if --provider given)
        # ----------------------------------------------------------------
        registry = _build_default_registry()
        all_providers = registry.enabled_providers()

        if provider_filter is not None:
            providers = [p for p in all_providers if p.name == provider_filter]
            if not providers:
                logger.warning(
                    "run_enrichment_cron: unknown provider '%s' — no providers matched",
                    provider_filter,
                )
                self.stdout.write(
                    self.style.WARNING(
                        f"Unknown provider '{provider_filter}'. No enrichment performed."
                    )
                )
                return
        else:
            providers = all_providers

        # ----------------------------------------------------------------
        # --person-id: single-person mode, bypass staleness
        # ----------------------------------------------------------------
        if person_id is not None:
            self._enrich_single(person_id, dry_run=dry_run)
            return

        # ----------------------------------------------------------------
        # Main loop: per-person staleness check
        # ----------------------------------------------------------------
        from src.web.persons.models import Person  # noqa: PLC0415

        total_processed = 0
        total_enriched = 0
        qs = Person.objects.order_by("pk")
        offset = 0

        while True:
            batch = list(qs[offset : offset + BATCH_SIZE])
            if not batch:
                break
            offset += BATCH_SIZE

            # Two queries for the whole batch replace per-person queries.
            runs_by_person = _prefetch_runs_for_batch(batch, providers)
            rejected_pks = _prefetch_rejected_person_ids(batch)
            now = timezone.now()

            for person in batch:
                if limit is not None and total_processed >= limit:
                    break

                stale = _stale_provider_names(person.pk, providers, runs_by_person, now)

                # Wikidata: skip if person has a rejected review
                if "wikidata" in stale and person.pk in rejected_pks:
                    stale = [n for n in stale if n != "wikidata"]
                    logger.info(
                        "run_enrichment_cron: skipping wikidata for %s (rejected review)",
                        person.pk,
                    )

                if not stale:
                    continue

                total_processed += 1
                if dry_run:
                    self.stdout.write(
                        f"[dry-run] Would enrich '{person.name}' ({person.pk}) "
                        f"with providers: {', '.join(stale)}"
                    )
                    continue

                logger.info(
                    "run_enrichment_cron: enriching person=%s providers=%s",
                    person.pk,
                    stale,
                )
                try:
                    run_enrichment_for_person(
                        person_id=str(person.pk),
                        triggered_by="cron",
                        provider_names=stale,
                    )
                    total_enriched += 1
                except Exception:
                    logger.exception(
                        "run_enrichment_cron: enrichment failed for person=%s", person.pk
                    )

            if limit is not None and total_processed >= limit:
                break

        suffix = " [dry-run]" if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"Done{suffix}. Persons processed: {total_processed}, enriched: {total_enriched}."
            )
        )
        logger.info(
            "run_enrichment_cron complete: processed=%s enriched=%s dry_run=%s",
            total_processed,
            total_enriched,
            dry_run,
        )

    def _enrich_single(self, person_id: str, *, dry_run: bool) -> None:
        """Enrich a single person by ID, bypassing staleness."""
        from src.web.persons.models import Person  # noqa: PLC0415

        try:
            person = Person.objects.get(pk=person_id)
        except Person.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Person {person_id!r} not found."))
            return

        if dry_run:
            self.stdout.write(
                f"[dry-run] Would enrich '{person.name}' ({person.pk}) with all providers."
            )
            return

        logger.info("run_enrichment_cron: enriching single person=%s (all providers)", person.pk)
        run_enrichment_for_person(
            person_id=str(person.pk),
            triggered_by="cron",
            provider_names=None,
        )
        self.stdout.write(self.style.SUCCESS(f"Enriched '{person.name}'."))
