"""Data migration: seed P2390 (Ballotpedia ID) into ExternalIdentifierProperty.

P2390 is excluded from sync_wikidata_properties because it lacks the subject-type
constraint pattern that the SPARQL query filters on.  This migration seeds the row
directly so that WikidataProvider can extract and persist the ballotpedia-slug
attribute for persons with a P2390 claim.

The migration is idempotent via update_or_create — safe to run on a DB that
already has the row from a future improved sync.
"""

from django.db import migrations


def seed_ballotpedia_property(apps, schema_editor):
    """Upsert the P2390 / Ballotpedia ID ExternalIdentifierProperty row."""
    ExternalIdentifierProperty = apps.get_model("persons", "ExternalIdentifierProperty")
    ExternalPlatform = apps.get_model("persons", "ExternalPlatform")

    platform = ExternalPlatform.objects.filter(slug="ballotpedia").first()

    ExternalIdentifierProperty.objects.update_or_create(
        wikidata_property_id="P2390",
        defaults={
            "slug": "ballotpedia-slug",
            "display": "Ballotpedia page slug",
            "description": "Ballotpedia page slug for a person",
            "formatter_url": "https://ballotpedia.org/$1",
            "subject_item_label": "Ballotpedia",
            "taxonomy_categories": [],
            "is_enabled": True,
            "sort_order": 140,
            "platform": platform,
        },
    )


class Migration(migrations.Migration):
    """Seed P2390 Ballotpedia identifier property."""

    dependencies = [
        ("persons", "0014_add_wikidatacandidatereview"),
    ]

    operations = [
        migrations.RunPython(
            seed_ballotpedia_property,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
