"""Data migration: pre-populate default AttributeLabel and SocialPlatform rows."""

from django.db import migrations

DEFAULT_LABELS = [
    # (value_type, slug, display, sort_order)
    ("email", "work", "Work", 0),
    ("email", "home", "Home", 1),
    ("email", "personal", "Personal", 2),
    ("phone", "work", "Work", 0),
    ("phone", "home", "Home", 1),
    ("phone", "mobile", "Mobile", 2),
    ("phone", "personal", "Personal", 3),
    ("url", "website", "Website", 0),
    ("url", "blog", "Blog", 1),
    ("url", "work", "Work", 2),
    ("platform_url", "website", "Website", 0),
    ("platform_url", "blog", "Blog", 1),
    ("platform_url", "work", "Work", 2),
    ("location", "home", "Home", 0),
    ("location", "work", "Work", 1),
    ("location", "current", "Current", 2),
    ("location", "previous", "Previous", 3),
    ("location", "mailing", "Mailing", 4),
]

DEFAULT_PLATFORMS = [
    # (slug, display, sort_order)
    ("linkedin", "LinkedIn", 0),
    ("github", "GitHub", 1),
    ("twitter", "Twitter / X", 2),
    ("instagram", "Instagram", 3),
    ("facebook", "Facebook", 4),
    ("youtube", "YouTube", 5),
    ("tiktok", "TikTok", 6),
]


def populate_defaults(apps, schema_editor):
    """Insert default AttributeLabel and SocialPlatform rows."""
    AttributeLabel = apps.get_model("persons", "AttributeLabel")
    SocialPlatform = apps.get_model("persons", "SocialPlatform")

    AttributeLabel.objects.bulk_create(
        [
            AttributeLabel(
                value_type=vt,
                slug=slug,
                display=display,
                sort_order=order,
                is_active=True,
            )
            for vt, slug, display, order in DEFAULT_LABELS
        ],
        ignore_conflicts=True,
    )

    SocialPlatform.objects.bulk_create(
        [
            SocialPlatform(
                slug=slug,
                display=display,
                sort_order=order,
                is_active=True,
            )
            for slug, display, order in DEFAULT_PLATFORMS
        ],
        ignore_conflicts=True,
    )


def remove_defaults(apps, schema_editor):
    """Remove the default rows inserted by this migration."""
    AttributeLabel = apps.get_model("persons", "AttributeLabel")
    SocialPlatform = apps.get_model("persons", "SocialPlatform")

    slugs_by_type: dict[str, list[str]] = {}
    for vt, slug, _, _ in DEFAULT_LABELS:
        slugs_by_type.setdefault(vt, []).append(slug)
    for vt, slugs in slugs_by_type.items():
        AttributeLabel.objects.filter(value_type=vt, slug__in=slugs).delete()

    platform_slugs = [slug for slug, _, _ in DEFAULT_PLATFORMS]
    SocialPlatform.objects.filter(slug__in=platform_slugs).delete()


class Migration(migrations.Migration):
    """Pre-populate default AttributeLabel and SocialPlatform rows."""

    dependencies = [
        ("persons", "0004_attributelabel_socialplatform_personattribute_typed"),
    ]

    operations = [
        migrations.RunPython(populate_defaults, reverse_code=remove_defaults),
    ]
