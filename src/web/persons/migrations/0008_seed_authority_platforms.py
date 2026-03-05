"""Data migration: seed additional ExternalPlatform authority identity records."""

from django.db import migrations

NEW_PLATFORMS = [
    {"slug": "wikidata", "display": "Wikidata", "sort_order": 100},
    {"slug": "wikipedia", "display": "Wikipedia", "sort_order": 101},
    {"slug": "viaf", "display": "VIAF", "sort_order": 110},
    {"slug": "isni", "display": "ISNI", "sort_order": 111},
    {"slug": "loc", "display": "Library of Congress", "sort_order": 112},
    {"slug": "gnd", "display": "GND", "sort_order": 113},
    {"slug": "orcid", "display": "ORCID", "sort_order": 120},
    {"slug": "imdb", "display": "IMDb", "sort_order": 130},
    {"slug": "musicbrainz", "display": "MusicBrainz", "sort_order": 131},
    {"slug": "ballotpedia", "display": "Ballotpedia", "sort_order": 140},
    {"slug": "opensecrets", "display": "OpenSecrets", "sort_order": 141},
]


def seed_authority_platforms(apps, schema_editor):
    """Insert authority/identity ExternalPlatform rows."""
    ExternalPlatform = apps.get_model("persons", "ExternalPlatform")
    slugs_to_add = [p["slug"] for p in NEW_PLATFORMS]
    existing = set(
        ExternalPlatform.objects.filter(slug__in=slugs_to_add).values_list("slug", flat=True)
    )
    ExternalPlatform.objects.bulk_create(
        [ExternalPlatform(**p) for p in NEW_PLATFORMS if p["slug"] not in existing]
    )


def remove_authority_platforms(apps, schema_editor):
    """Reverse: remove the seeded authority platform rows."""
    ExternalPlatform = apps.get_model("persons", "ExternalPlatform")
    ExternalPlatform.objects.filter(slug__in=[p["slug"] for p in NEW_PLATFORMS]).delete()


class Migration(migrations.Migration):
    """Seed authority identity ExternalPlatform rows."""

    dependencies = [
        ("persons", "0007_rename_socialplatform_externalplatform"),
    ]

    operations = [
        migrations.RunPython(
            seed_authority_platforms,
            reverse_code=remove_authority_platforms,
        ),
    ]
