"""Person and PersonName models."""

from django.db import models

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
        )
