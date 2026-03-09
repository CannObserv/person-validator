"""Management command: sync_wikidata_properties.

Queries Wikidata SPARQL for all external identifier properties applicable
to human persons (Q5 subject-type constraint) and upserts them into
ExternalIdentifierProperty. After each upsert, attempts to auto-link the
property to an existing ExternalPlatform by matching slug.
"""

import re
import time
from datetime import timedelta

import requests
from django.core.management.base import BaseCommand
from django.db.models import Max
from django.utils import timezone

from src.core.logging import configure_logging, get_logger
from src.web.persons.models import ExternalIdentifierProperty, ExternalPlatform

logger = get_logger(__name__)

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "PersonValidator/0.1 (greg@cannabis.observer)"
PAGE_SIZE = 500
MAX_RETRIES = 3

SPARQL_TEMPLATE = """
SELECT DISTINCT
  ?prop ?propLabel ?propDescription ?formatterURL ?subjectItemLabel
  (GROUP_CONCAT(DISTINCT ?catQID; separator="|") AS ?categories)
WHERE {{
  ?prop wikibase:propertyType wikibase:ExternalId .
  ?prop p:P2302 [ ps:P2302 wd:Q21503250 ; pq:P2308 wd:Q5 ] .
  OPTIONAL {{ ?prop wdt:P1630 ?formatterURL . }}
  OPTIONAL {{
    ?prop wdt:P1629 ?subjectItem .
    ?subjectItem rdfs:label ?subjectItemLabel .
    FILTER(LANG(?subjectItemLabel) = "en")
  }}
  OPTIONAL {{
    ?prop wdt:P31 ?cat .
    BIND(STR(?cat) AS ?catQID)
  }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}}
GROUP BY ?prop ?propLabel ?propDescription ?formatterURL ?subjectItemLabel
ORDER BY ?prop
LIMIT {limit}
OFFSET {offset}
"""


def generate_slug(label: str) -> str:
    """Derive a slug from an English property label.

    Lowercases, replaces spaces with hyphens, strips non-alphanumeric-hyphen
    characters, and collapses consecutive hyphens.
    """
    slug = label.lower()
    slug = re.sub(r"[^a-z0-9\s-]", " ", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug


_QID_RE = re.compile(r"^[PQ]\d+$")


def _extract_qid(uri: str) -> str:
    """Extract the QID/PID from a Wikidata entity URI, e.g. 'Q19595382'.

    Returns an empty string if the extracted token does not match the
    expected QID/PID format (e.g. malformed or trailing-slash URIs).
    """
    token = uri.rstrip("/").split("/")[-1]
    return token if _QID_RE.match(token) else ""


def _fetch_page(offset: int, limit: int) -> list[dict]:
    """Fetch a single SPARQL results page with retry/backoff."""
    query = SPARQL_TEMPLATE.format(limit=limit, offset=offset)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                SPARQL_ENDPOINT,
                params={"query": query, "format": "json"},
                headers={"User-Agent": USER_AGENT},
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["results"]["bindings"]
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response else None
            if status in (429, 503) and attempt < MAX_RETRIES:
                wait = 2**attempt
                logger.warning(
                    "Wikidata SPARQL transient error: status=%s attempt=%s wait=%ss",
                    status,
                    attempt,
                    wait,
                )
                time.sleep(wait)
            else:
                raise
    return []  # unreachable, but satisfies type checker


def _parse_row(row: dict) -> dict:
    """Parse a SPARQL binding row into a flat dict of field values."""
    prop_uri = row["prop"]["value"]
    property_id = _extract_qid(prop_uri)  # e.g. "P214"

    label = row.get("propLabel", {}).get("value", "")
    description = row.get("propDescription", {}).get("value", "")
    formatter_url = row.get("formatterURL", {}).get("value", "")
    subject_item_label = row.get("subjectItemLabel", {}).get("value", "")
    categories_raw = row.get("categories", {}).get("value", "")

    categories: list[str] = []
    if categories_raw:
        for uri in categories_raw.split("|"):
            uri = uri.strip()
            if uri:
                qid = _extract_qid(uri)
                if qid and qid not in categories:
                    categories.append(qid)

    return {
        "property_id": property_id,
        "label": label,
        "description": description,
        "formatter_url": formatter_url,
        "subject_item_label": subject_item_label,
        "taxonomy_categories": categories,
    }


def _resolve_slug(label: str, property_id: str) -> str:
    """Generate a slug for the property, handling collisions.

    If the base slug collides with a different property, appends
    ``-{property_id_lower}`` (e.g. ``viaf-cluster-id-p214``). If the
    fallback slug also collides, appends a numeric suffix until unique.
    """
    base_slug = generate_slug(label)
    taken = set(
        ExternalIdentifierProperty.objects.filter(slug__startswith=base_slug)
        .exclude(wikidata_property_id=property_id)
        .values_list("slug", flat=True)
    )
    if base_slug not in taken:
        return base_slug
    fallback = f"{base_slug}-{property_id.lower()}"
    if fallback not in taken:
        return fallback
    # Last-resort: numeric suffix
    i = 2
    while f"{fallback}-{i}" in taken:
        i += 1
    return f"{fallback}-{i}"


def _auto_link_platform(prop: ExternalIdentifierProperty) -> bool:
    """Attempt to link prop to an active ExternalPlatform by slug. Returns True if linked."""
    if prop.platform_id is not None:
        return False
    platform = ExternalPlatform.objects.filter(slug=prop.slug, is_active=True).first()
    if platform:
        prop.platform = platform
        prop.save(update_fields=["platform"])
        return True
    return False


class Command(BaseCommand):
    """Sync Wikidata external identifier properties into ExternalIdentifierProperty."""

    help = "Fetch and upsert Wikidata external identifier properties for human persons."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=PAGE_SIZE,
            help="Page size for SPARQL pagination (default: 500).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Fetch and report counts without writing to the database.",
        )

    def handle(self, *args, **options):
        configure_logging()
        limit = options["limit"]
        dry_run = options["dry_run"]
        offset = 0
        created = updated = skipped = warnings = auto_linked = 0

        # 24h guard: skip if a sync completed within the past 24 hours.
        # Guard is bypassed when last_synced_at is NULL (fresh deployment or empty table).
        last_sync = ExternalIdentifierProperty.objects.aggregate(
            latest=Max("last_synced_at")
        )["latest"]
        if last_sync is not None and (timezone.now() - last_sync) < timedelta(hours=24):
            logger.info(
                "sync_wikidata_properties: last sync was %s ago — skipping (24h guard)",
                timezone.now() - last_sync,
            )
            return

        self.stdout.write(
            f"{'[dry-run] ' if dry_run else ''}Fetching Wikidata external identifier properties..."
        )

        while True:
            now = timezone.now()
            rows = _fetch_page(offset, limit)
            if not rows:
                break

            for row in rows:
                try:
                    parsed = _parse_row(row)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to parse SPARQL row: %s — %s", exc, row)
                    warnings += 1
                    continue

                property_id = parsed["property_id"]
                label = parsed["label"]

                if not property_id or not label:
                    skipped += 1
                    continue

                slug = _resolve_slug(label, property_id)

                existing = ExternalIdentifierProperty.objects.filter(
                    wikidata_property_id=property_id
                ).first()

                if existing is None:
                    created += 1
                    if not dry_run:
                        prop = ExternalIdentifierProperty.objects.create(
                            wikidata_property_id=property_id,
                            slug=slug,
                            display=label,
                            description=parsed["description"],
                            formatter_url=parsed["formatter_url"],
                            subject_item_label=parsed["subject_item_label"],
                            taxonomy_categories=parsed["taxonomy_categories"],
                            last_synced_at=now,
                        )
                        if _auto_link_platform(prop):
                            auto_linked += 1
                else:
                    updated += 1
                    if not dry_run:
                        # Update all fields except is_enabled
                        existing.slug = slug
                        existing.display = label
                        existing.description = parsed["description"]
                        existing.formatter_url = parsed["formatter_url"]
                        existing.subject_item_label = parsed["subject_item_label"]
                        existing.taxonomy_categories = parsed["taxonomy_categories"]
                        existing.last_synced_at = now
                        existing.save(
                            update_fields=[
                                "slug",
                                "display",
                                "description",
                                "formatter_url",
                                "subject_item_label",
                                "taxonomy_categories",
                                "last_synced_at",
                            ]
                        )
                        if _auto_link_platform(existing):
                            auto_linked += 1

            if len(rows) < limit:
                break
            offset += limit

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created {created}, Updated {updated}, "
                f"Skipped {skipped}, Auto-linked {auto_linked}, Warnings {warnings}."
            )
        )
        logger.info(
            "sync_wikidata_properties complete: created=%s updated=%s skipped=%s "
            "auto_linked=%s warnings=%s",
            created,
            updated,
            skipped,
            auto_linked,
            warnings,
        )
