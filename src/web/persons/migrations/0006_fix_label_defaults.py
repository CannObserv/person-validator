"""Data migration: align AttributeLabel defaults with GH issue #9 specification.

Changes from the original 0005 migration:
- email: remove 'home' label
- platform_url: remove 'website' and 'blog' labels; add 'personal'
"""

from django.db import migrations

# Labels to remove: list of (value_type, slug)
REMOVE_LABELS = [
    ("email", "home"),
    ("platform_url", "website"),
    ("platform_url", "blog"),
]

# Labels to add: list of (value_type, slug, display, sort_order)
ADD_LABELS = [
    ("platform_url", "personal", "Personal", 1),
]


def fix_labels(apps, schema_editor):
    """Remove stale labels and add missing ones."""
    AttributeLabel = apps.get_model("persons", "AttributeLabel")

    for value_type, slug in REMOVE_LABELS:
        AttributeLabel.objects.filter(value_type=value_type, slug=slug).delete()

    AttributeLabel.objects.bulk_create(
        [
            AttributeLabel(
                value_type=vt,
                slug=slug,
                display=display,
                sort_order=order,
                is_active=True,
            )
            for vt, slug, display, order in ADD_LABELS
        ],
        ignore_conflicts=True,
    )

    # Re-sequence sort_order for platform_url to be clean after the removals.
    for order, slug in enumerate(["work", "personal"]):
        AttributeLabel.objects.filter(value_type="platform_url", slug=slug).update(sort_order=order)


def reverse_fix_labels(apps, schema_editor):
    """Restore the pre-fix state."""
    AttributeLabel = apps.get_model("persons", "AttributeLabel")

    # Remove labels that were added by this migration.
    for value_type, slug, _, _ in ADD_LABELS:
        AttributeLabel.objects.filter(value_type=value_type, slug=slug).delete()

    # Restore the labels that were removed.
    AttributeLabel.objects.bulk_create(
        [
            AttributeLabel(
                value_type="email", slug="home", display="Home", sort_order=1, is_active=True
            ),
            AttributeLabel(
                value_type="platform_url",
                slug="website",
                display="Website",
                sort_order=0,
                is_active=True,
            ),
            AttributeLabel(
                value_type="platform_url", slug="blog", display="Blog", sort_order=1, is_active=True
            ),
        ],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    """Align AttributeLabel defaults with GH issue #9 specification."""

    dependencies = [
        ("persons", "0005_default_labels_and_platforms"),
    ]

    operations = [
        migrations.RunPython(fix_labels, reverse_code=reverse_fix_labels),
    ]
