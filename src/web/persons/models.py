"""Person, PersonName, PersonAttribute, AttributeLabel, and ExternalPlatform models."""

# VALUE_TYPE_CHOICES is defined in src/core/enrichment/attribute_types.py and
# imported here so the canonical list lives in one place.

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from src.core.enrichment.attribute_types import VALUE_TYPE_CHOICES
from src.core.fields import ULIDField

NAME_TYPE_CHOICES = [
    ("primary", "Primary"),
    ("birth", "Birth"),
    ("maiden", "Maiden"),
    ("married", "Married"),
    ("former", "Former"),
    ("alias", "Alias"),
    ("nickname", "Nickname"),
    ("professional", "Professional"),
    ("transliteration", "Transliteration"),
    ("abbreviation", "Abbreviation"),
    ("misspelling", "Misspelling"),
]


class Person(models.Model):
    """Identity anchor for a real-world individual.

    Denormalized name fields are kept in sync with the primary PersonName.
    """

    id = ULIDField(primary_key=True)
    name = models.CharField(max_length=500)
    given_name = models.CharField(max_length=255, null=True, blank=True)
    middle_name = models.CharField(max_length=255, null=True, blank=True)
    surname = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "persons_person"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class PersonName(models.Model):
    """Every known name variant for a person."""

    id = ULIDField(primary_key=True)
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="names",
    )
    name_type = models.CharField(max_length=30, choices=NAME_TYPE_CHOICES)
    full_name = models.CharField(max_length=500)
    given_name = models.CharField(max_length=255, null=True, blank=True)
    middle_name = models.CharField(max_length=255, null=True, blank=True)
    surname = models.CharField(max_length=255, null=True, blank=True)
    prefix = models.CharField(max_length=50, null=True, blank=True)
    suffix = models.CharField(max_length=50, null=True, blank=True)
    is_primary = models.BooleanField(default=False)
    source = models.CharField(max_length=100)
    effective_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        null=True,
        blank=True,
        help_text=(
            "Certainty score [0.0\u20131.0] for this name record. "
            "Null = unscored (e.g. manually entered)."
        ),
    )
    provenance = models.JSONField(
        null=True,
        blank=True,
        help_text=(
            "Structured provenance metadata. Schema is provider-dependent. "
            "Common keys: provider (str), retrieved_at (ISO 8601 str), "
            "source_url (str), wikidata_qid (str), wikidata_alias_lang (str)."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "persons_personname"
        ordering = ["-is_primary", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["person"],
                condition=models.Q(is_primary=True),
                name="unique_primary_per_person",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.name_type})"

    def save(self, *args, **kwargs):
        """Handle primary demotion and sync to Person."""
        if self.is_primary:
            # Demote any existing primary for this person (excluding self)
            PersonName.objects.filter(
                person=self.person,
                is_primary=True,
            ).exclude(pk=self.pk).update(
                is_primary=False,
                name_type="former",
                updated_at=timezone.now(),
            )
        super().save(*args, **kwargs)
        if self.is_primary:
            self._sync_to_person()

    def _sync_to_person(self):
        """Sync primary name fields to the parent Person."""
        Person.objects.filter(pk=self.person_id).update(
            name=self.full_name,
            given_name=self.given_name,
            middle_name=self.middle_name,
            surname=self.surname,
            updated_at=timezone.now(),
        )


class AttributeLabel(models.Model):
    """Controlled vocabulary of labels scoped per value_type.

    Labels are stored as a JSON array in PersonAttribute.metadata["label"].
    Each label is scoped to a specific value_type (email, phone, url,
    platform_url, location).
    """

    value_type = models.CharField(max_length=50)
    slug = models.SlugField(max_length=50)
    display = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "persons_attributelabel"
        unique_together = [("value_type", "slug")]
        ordering = ["value_type", "sort_order", "slug"]

    def __str__(self) -> str:
        return f"{self.value_type}/{self.slug}"


class ExternalPlatform(models.Model):
    """Controlled vocabulary of external platform/identity identifiers for platform_url."""

    slug = models.SlugField(max_length=50, unique=True)
    display = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "persons_externalplatform"
        ordering = ["sort_order", "slug"]

    def __str__(self) -> str:
        return self.display


class PersonAttribute(models.Model):
    """Enrichment data about a person (append-only EAV)."""

    id = ULIDField(primary_key=True)
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="attributes",
    )
    source = models.CharField(max_length=200)
    key = models.CharField(max_length=200)
    value = models.TextField()
    value_type = models.CharField(
        max_length=50,
        choices=VALUE_TYPE_CHOICES,
        default="text",
        db_index=True,
    )
    metadata = models.JSONField(null=True, blank=True)
    confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "persons_personattribute"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.key}: {self.value}"


class ExternalIdentifierProperty(models.Model):
    """
    A Wikidata external identifier property applicable to human persons.

    Populated and refreshed by the `sync_wikidata_properties` management command.
    Used by WikidataProvider to determine which properties to extract and
    how to construct platform_url values via formatter_url.

    The `is_enabled` flag allows administrators to narrow which properties
    WikidataProvider actively extracts. All imported properties are enabled
    by default; disable selectively to suppress noisy or low-value identifiers.

    Namespace note: `slug` here is independent of `ExternalPlatform.slug`.
    When a corresponding ExternalPlatform exists (e.g. slug="viaf"), link it
    via `platform` FK. WikidataProvider uses this FK to associate extracted
    identifier values with the correct ExternalPlatform when creating
    platform_url attributes.
    """

    wikidata_property_id = models.CharField(
        max_length=20,
        unique=True,
        help_text='Wikidata property ID, e.g. "P214"',
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-safe identifier derived from English property label.",
    )
    display = models.CharField(max_length=200, help_text="English property label.")
    description = models.TextField(blank=True, help_text="English property description.")
    formatter_url = models.URLField(
        max_length=1000,
        blank=True,
        help_text="P1630 value. Replace $1 with the identifier value to get the URL.",
    )
    subject_item_label = models.CharField(
        max_length=200,
        blank=True,
        help_text="English label of the P1629 subject item (the database/system).",
    )
    taxonomy_categories = models.JSONField(
        default=list,
        help_text="List of Wikidata QIDs (P31 values) classifying this property.",
    )
    platform = models.ForeignKey(
        "ExternalPlatform",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="identifier_properties",
        help_text="Linked ExternalPlatform, if one exists for this identifier system.",
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text="When False, WikidataProvider skips this property during extraction.",
    )
    sort_order = models.PositiveIntegerField(default=0)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "persons_externalidentifierproperty"
        ordering = ["sort_order", "wikidata_property_id"]
        verbose_name = "External Identifier Property"
        verbose_name_plural = "External Identifier Properties"

    def __str__(self) -> str:
        return f"{self.wikidata_property_id} \u2014 {self.display}"

    def build_url(self, identifier_value: str) -> str | None:
        """Return the full URL for the given identifier value, or None if no formatter_url."""
        if not self.formatter_url:
            return None
        return self.formatter_url.replace("$1", identifier_value)


class EnrichmentRun(models.Model):
    """Audit log record for a single provider run against a person."""

    STATUS_CHOICES = [
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
        ("no_match", "No Match"),
    ]

    TRIGGERED_BY_CHOICES = [
        ("cron", "Cron"),
        ("adjudication", "Adjudication"),
        ("manual", "Manual"),
        ("api", "API"),
    ]

    id = ULIDField(primary_key=True)
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="enrichment_runs")
    provider = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    attributes_saved = models.PositiveIntegerField(default=0)
    attributes_skipped = models.PositiveIntegerField(default=0)
    warnings = models.JSONField(default=list)
    error = models.TextField(blank=True)
    triggered_by = models.CharField(
        max_length=20, choices=TRIGGERED_BY_CHOICES, blank=True, default="manual"
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
