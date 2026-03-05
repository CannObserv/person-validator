"""Tests for Person and PersonName models."""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection
from django.utils import timezone
from ulid import ULID

from src.core.fields import ULIDField
from src.web.persons.models import (
    NAME_TYPE_CHOICES,
    AttributeLabel,
    ExternalPlatform,
    Person,
    PersonAttribute,
    PersonName,
)


@pytest.mark.django_db
class TestPersonModel:
    """Tests for the Person model."""

    def test_create_person(self):
        """A Person can be created with just a name."""
        person = Person.objects.create(name="Jane Doe")
        assert person.pk is not None
        assert len(person.pk) == 26
        assert person.name == "Jane Doe"

    def test_person_pk_is_ulid_field(self):
        """Person.id should be a ULIDField primary key."""
        field = Person._meta.get_field("id")
        assert isinstance(field, ULIDField)
        assert field.primary_key is True

    def test_person_nullable_name_parts(self):
        """given_name, middle_name, surname are nullable."""
        person = Person.objects.create(name="Mononym")
        assert person.given_name is None
        assert person.middle_name is None
        assert person.surname is None

    def test_person_with_name_parts(self):
        """Person can be created with all name parts."""
        person = Person.objects.create(
            name="Jane Marie Doe",
            given_name="Jane",
            middle_name="Marie",
            surname="Doe",
        )
        person.refresh_from_db()
        assert person.given_name == "Jane"
        assert person.middle_name == "Marie"
        assert person.surname == "Doe"

    def test_person_timestamps(self):
        """created_at and updated_at are set automatically."""
        person = Person.objects.create(name="Jane Doe")
        assert person.created_at is not None
        assert person.updated_at is not None

    def test_person_timestamps_are_utc(self):
        """Timestamps must be timezone-aware and in UTC."""
        person = Person.objects.create(name="Jane Doe")
        person.refresh_from_db()
        assert person.created_at.tzinfo is not None
        assert person.created_at.utcoffset() == timedelta(0)
        assert person.updated_at.tzinfo is not None
        assert person.updated_at.utcoffset() == timedelta(0)

    def test_person_str(self):
        """String representation is the display name."""
        person = Person.objects.create(name="Jane Doe")
        assert str(person) == "Jane Doe"


@pytest.mark.django_db
class TestPersonNameModel:
    """Tests for the PersonName model."""

    def test_create_person_name(self):
        """A PersonName can be created linked to a Person."""
        person = Person.objects.create(name="Jane Doe")
        pn = PersonName.objects.create(
            person=person,
            name_type="primary",
            full_name="Jane Doe",
            is_primary=True,
            source="manual",
        )
        assert pn.pk is not None
        assert len(pn.pk) == 26

    def test_person_name_pk_is_ulid_field(self):
        """PersonName.id should be a ULIDField primary key."""
        field = PersonName._meta.get_field("id")
        assert isinstance(field, ULIDField)
        assert field.primary_key is True

    def test_person_name_cascade_delete(self):
        """Deleting a Person cascades to PersonName."""
        person = Person.objects.create(name="Jane Doe")
        PersonName.objects.create(
            person=person,
            name_type="primary",
            full_name="Jane Doe",
            is_primary=True,
            source="manual",
        )
        person_id = person.pk
        person.delete()
        assert PersonName.objects.filter(person_id=person_id).count() == 0

    def test_person_name_nullable_fields(self):
        """Optional fields default to None/blank."""
        person = Person.objects.create(name="Mononym")
        pn = PersonName.objects.create(
            person=person,
            name_type="primary",
            full_name="Mononym",
            is_primary=True,
            source="manual",
        )
        pn.refresh_from_db()
        assert pn.given_name is None
        assert pn.middle_name is None
        assert pn.surname is None
        assert pn.prefix is None
        assert pn.suffix is None
        assert pn.effective_date is None
        assert pn.end_date is None
        assert pn.notes is None

    def test_person_name_str(self):
        """String representation is the full_name."""
        person = Person.objects.create(name="Jane Doe")
        pn = PersonName.objects.create(
            person=person,
            name_type="primary",
            full_name="Jane Marie Doe",
            is_primary=True,
            source="manual",
        )
        assert str(pn) == "Jane Marie Doe (primary)"

    def test_person_name_timestamps(self):
        """created_at and updated_at are set automatically."""
        person = Person.objects.create(name="Jane Doe")
        pn = PersonName.objects.create(
            person=person,
            name_type="primary",
            full_name="Jane Doe",
            is_primary=True,
            source="manual",
        )
        assert pn.created_at is not None
        assert pn.updated_at is not None


class TestNameTypeChoices:
    """Test that all documented name types are present."""

    EXPECTED_TYPES = [
        "primary",
        "birth",
        "maiden",
        "married",
        "former",
        "alias",
        "nickname",
        "professional",
        "transliteration",
        "abbreviation",
        "misspelling",
    ]

    def test_all_name_types_present(self):
        """Every documented name type exists in the choices."""
        choice_values = [v for v, _ in NAME_TYPE_CHOICES]
        for nt in self.EXPECTED_TYPES:
            assert nt in choice_values, f"Missing name type: {nt}"

    def test_name_type_count(self):
        """Choices should have exactly the documented number of types."""
        assert len(NAME_TYPE_CHOICES) == 11


@pytest.mark.django_db
class TestPrimarySync:
    """Test primary name sync to Person denormalized fields."""

    def test_primary_sync_on_create(self):
        """Creating a primary PersonName syncs fields to Person."""
        person = Person.objects.create(name="Placeholder")
        PersonName.objects.create(
            person=person,
            name_type="primary",
            full_name="Jane Marie Doe",
            given_name="Jane",
            middle_name="Marie",
            surname="Doe",
            is_primary=True,
            source="manual",
        )
        person.refresh_from_db()
        assert person.name == "Jane Marie Doe"
        assert person.given_name == "Jane"
        assert person.middle_name == "Marie"
        assert person.surname == "Doe"

    def test_primary_sync_on_update(self):
        """Updating a primary PersonName re-syncs to Person."""
        person = Person.objects.create(name="Old Name")
        pn = PersonName.objects.create(
            person=person,
            name_type="primary",
            full_name="Old Name",
            is_primary=True,
            source="manual",
        )
        pn.full_name = "New Name"
        pn.given_name = "New"
        pn.surname = "Name"
        pn.save()
        person.refresh_from_db()
        assert person.name == "New Name"
        assert person.given_name == "New"
        assert person.surname == "Name"

    def test_primary_sync_updates_person_updated_at(self):
        """Syncing a primary PersonName advances Person.updated_at."""
        person = Person.objects.create(name="Placeholder")
        # Push created timestamp into the past so the delta is unambiguous
        Person.objects.filter(pk=person.pk).update(
            updated_at=timezone.now() - timedelta(seconds=10)
        )
        person.refresh_from_db()
        old_updated = person.updated_at
        PersonName.objects.create(
            person=person,
            name_type="primary",
            full_name="Jane Doe",
            is_primary=True,
            source="manual",
        )
        person.refresh_from_db()
        assert person.updated_at > old_updated

    def test_non_primary_does_not_sync(self):
        """Creating a non-primary PersonName does NOT sync to Person."""
        person = Person.objects.create(name="Original")
        PersonName.objects.create(
            person=person,
            name_type="alias",
            full_name="Alias Name",
            is_primary=False,
            source="manual",
        )
        person.refresh_from_db()
        assert person.name == "Original"


@pytest.mark.django_db
class TestPrimaryDemotion:
    """Test that assigning a new primary demotes the old one."""

    def test_old_primary_demoted(self):
        """When a new primary is saved, the old primary is demoted."""
        person = Person.objects.create(name="Jane Doe")
        old_pn = PersonName.objects.create(
            person=person,
            name_type="primary",
            full_name="Jane Doe",
            is_primary=True,
            source="manual",
        )
        PersonName.objects.create(
            person=person,
            name_type="primary",
            full_name="Jane Smith",
            is_primary=True,
            source="manual",
        )
        old_pn.refresh_from_db()
        assert old_pn.is_primary is False
        assert old_pn.name_type == "former"

    def test_new_primary_syncs_to_person(self):
        """The new primary's fields are synced to Person."""
        person = Person.objects.create(name="Jane Doe")
        PersonName.objects.create(
            person=person,
            name_type="primary",
            full_name="Jane Doe",
            given_name="Jane",
            surname="Doe",
            is_primary=True,
            source="manual",
        )
        PersonName.objects.create(
            person=person,
            name_type="primary",
            full_name="Jane Smith",
            given_name="Jane",
            surname="Smith",
            is_primary=True,
            source="manual",
        )
        person.refresh_from_db()
        assert person.name == "Jane Smith"
        assert person.surname == "Smith"

    def test_demoted_person_name_updated_at_advances(self):
        """Demoted PersonName's updated_at is refreshed."""
        person = Person.objects.create(name="Jane Doe")
        old_pn = PersonName.objects.create(
            person=person,
            name_type="primary",
            full_name="Jane Doe",
            is_primary=True,
            source="manual",
        )
        # Push into the past
        PersonName.objects.filter(pk=old_pn.pk).update(
            updated_at=timezone.now() - timedelta(seconds=10)
        )
        old_pn.refresh_from_db()
        old_ts = old_pn.updated_at
        PersonName.objects.create(
            person=person,
            name_type="primary",
            full_name="Jane Smith",
            is_primary=True,
            source="manual",
        )
        old_pn.refresh_from_db()
        assert old_pn.updated_at > old_ts

    def test_exactly_one_primary_after_demotion(self):
        """After demotion there is exactly one primary PersonName."""
        person = Person.objects.create(name="Jane Doe")
        PersonName.objects.create(
            person=person,
            name_type="primary",
            full_name="Jane Doe",
            is_primary=True,
            source="manual",
        )
        PersonName.objects.create(
            person=person,
            name_type="primary",
            full_name="Jane Smith",
            is_primary=True,
            source="manual",
        )
        assert PersonName.objects.filter(person=person, is_primary=True).count() == 1


@pytest.mark.django_db
class TestUniquePrimaryConstraint:
    """Test database-level unique constraint on is_primary per person."""

    def test_constraint_prevents_duplicate_primary_at_db_level(self):
        """Cannot have two is_primary=True for the same person at DB level.

        Note: The save() override handles demotion, so this tests the raw
        DB constraint by using bulk_create / raw update to bypass save().
        """
        person = Person.objects.create(name="Jane Doe")
        PersonName.objects.create(
            person=person,
            name_type="primary",
            full_name="Jane Doe",
            is_primary=True,
            source="manual",
        )
        # Bypass the save() override by using raw SQL
        with connection.cursor() as cursor:
            with pytest.raises(IntegrityError):
                cursor.execute(
                    "INSERT INTO persons_personname "
                    "(id, person_id, name_type, full_name, is_primary, source, "
                    "created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                    ["01AAAAAAAAAAAAAAAAAAAAAAA1", person.pk, "primary", "Dup", True, "manual"],
                )

    def test_multiple_non_primary_allowed(self):
        """Multiple is_primary=False for the same person is fine."""
        person = Person.objects.create(name="Jane Doe")
        PersonName.objects.create(
            person=person,
            name_type="alias",
            full_name="JD",
            is_primary=False,
            source="manual",
        )
        PersonName.objects.create(
            person=person,
            name_type="nickname",
            full_name="Janie",
            is_primary=False,
            source="manual",
        )
        assert PersonName.objects.filter(person=person, is_primary=False).count() == 2


@pytest.mark.django_db
class TestAttributeLabel:
    """Tests for the AttributeLabel model."""

    def test_create_label(self):
        label = AttributeLabel.objects.create(
            value_type="email", slug="vip", display="VIP", sort_order=99
        )
        assert label.pk is not None
        assert str(label) == "email/vip"

    def test_unique_together_constraint(self):
        AttributeLabel.objects.create(value_type="email", slug="custom-unique", display="Custom")
        with pytest.raises(IntegrityError):
            AttributeLabel.objects.create(value_type="email", slug="custom-unique", display="Dupe")

    def test_different_type_same_slug_allowed(self):
        # "work" already exists for email from data migration; only create for a type without it
        label = AttributeLabel.objects.create(value_type="date", slug="work", display="Work")
        assert label.pk is not None

    def test_is_active_default_true(self):
        label = AttributeLabel.objects.create(value_type="email", slug="test-new-slug", display="X")
        assert label.is_active is True

    def test_active_filter(self):
        AttributeLabel.objects.create(
            value_type="email", slug="active-only", display="Active", is_active=True
        )
        AttributeLabel.objects.create(
            value_type="email", slug="inactive-only", display="Old", is_active=False
        )
        active = list(
            AttributeLabel.objects.filter(value_type="email", is_active=True).values_list(
                "slug", flat=True
            )
        )
        assert "active-only" in active
        assert "inactive-only" not in active


@pytest.mark.django_db
class TestExternalPlatform:
    """Tests for the ExternalPlatform model."""

    def test_create_platform(self):
        p = ExternalPlatform.objects.create(slug="mastodon", display="Mastodon", sort_order=99)
        assert p.pk is not None
        assert str(p) == "Mastodon"

    def test_unique_slug_constraint(self):
        ExternalPlatform.objects.create(slug="custom-platform", display="Custom")
        with pytest.raises(IntegrityError):
            ExternalPlatform.objects.create(slug="custom-platform", display="Dupe")

    def test_is_active_default_true(self):
        p = ExternalPlatform.objects.create(slug="bluesky", display="Bluesky")
        assert p.is_active is True

    def test_active_filter(self):
        ExternalPlatform.objects.create(slug="new-active-net", display="NewActive", is_active=True)
        ExternalPlatform.objects.create(slug="old-inactive-net", display="OldNet", is_active=False)
        active = list(
            ExternalPlatform.objects.filter(is_active=True).values_list("slug", flat=True)
        )
        assert "new-active-net" in active
        assert "old-inactive-net" not in active


@pytest.mark.django_db
class TestPersonAttribute:
    """Tests for PersonAttribute model."""

    def test_create_attribute(self):
        """Can create a PersonAttribute with valid data."""
        person = Person.objects.create(name="Jane Doe")
        attr = PersonAttribute.objects.create(
            person=person,
            source="test_provider",
            key="employer",
            value="Acme Corp",
            confidence=0.85,
        )
        assert attr.pk is not None
        assert attr.source == "test_provider"
        assert attr.key == "employer"
        assert attr.value == "Acme Corp"
        assert attr.confidence == 0.85

    def test_str_representation(self):
        """String representation is 'key: value'."""
        person = Person.objects.create(name="Jane Doe")
        attr = PersonAttribute.objects.create(
            person=person,
            source="test",
            key="employer",
            value="Acme",
            confidence=0.9,
        )
        assert str(attr) == "employer: Acme"

    def test_cascade_delete(self):
        """Deleting person cascades to attributes."""
        person = Person.objects.create(name="Jane Doe")
        PersonAttribute.objects.create(
            person=person,
            source="test",
            key="employer",
            value="Acme",
            confidence=0.9,
        )
        person.delete()
        assert PersonAttribute.objects.count() == 0

    def test_confidence_rejects_above_one(self):
        """Confidence > 1.0 should fail validation."""
        person = Person.objects.create(name="Jane Doe")
        attr = PersonAttribute(
            person=person,
            source="test",
            key="score",
            value="high",
            confidence=1.5,
        )
        with pytest.raises(ValidationError):
            attr.full_clean()

    def test_confidence_rejects_below_zero(self):
        """Confidence < 0.0 should fail validation."""
        person = Person.objects.create(name="Jane Doe")
        attr = PersonAttribute(
            person=person,
            source="test",
            key="score",
            value="low",
            confidence=-0.1,
        )
        with pytest.raises(ValidationError):
            attr.full_clean()

    def test_confidence_accepts_boundary_values(self):
        """Confidence 0.0 and 1.0 should be valid."""
        person = Person.objects.create(name="Jane Doe")
        for val in (0.0, 1.0):
            attr = PersonAttribute(
                person=person,
                source="test",
                key="score",
                value="ok",
                confidence=val,
            )
            attr.full_clean()  # Should not raise

    def test_db_table_name(self):
        """Table name should be persons_personattribute."""
        assert PersonAttribute._meta.db_table == "persons_personattribute"

    def test_value_type_defaults_to_text(self):
        """value_type defaults to 'text'."""
        person = Person.objects.create(name="Jane Doe")
        attr = PersonAttribute.objects.create(
            person=person, source="test", key="employer", value="Acme", confidence=0.9
        )
        assert attr.value_type == "text"

    def test_value_type_filter(self):
        """Attributes can be filtered by value_type."""
        person = Person.objects.create(name="Jane Doe")
        PersonAttribute.objects.create(
            person=person, source="t", key="e", value="a@b.com", confidence=1.0, value_type="email"
        )
        PersonAttribute.objects.create(
            person=person,
            source="t",
            key="p",
            value="+1234567890",
            confidence=1.0,
            value_type="phone",
        )
        assert PersonAttribute.objects.filter(value_type="email").count() == 1
        assert PersonAttribute.objects.filter(value_type="phone").count() == 1

    def test_metadata_stored_and_retrieved(self):
        """metadata JSONField round-trips correctly."""
        person = Person.objects.create(name="Jane Doe")
        meta = {"label": ["work"], "city": "Denver"}
        attr = PersonAttribute.objects.create(
            person=person,
            source="test",
            key="address",
            value="Denver, CO",
            confidence=0.8,
            value_type="location",
            metadata=meta,
        )
        attr.refresh_from_db()
        assert attr.metadata == meta

    def test_metadata_nullable(self):
        """metadata defaults to null."""
        person = Person.objects.create(name="Jane Doe")
        attr = PersonAttribute.objects.create(
            person=person, source="t", key="x", value="y", confidence=1.0
        )
        attr.refresh_from_db()
        assert attr.metadata is None

    def test_updated_at_auto_set(self):
        """updated_at is set automatically."""
        person = Person.objects.create(name="Jane Doe")
        attr = PersonAttribute.objects.create(
            person=person, source="t", key="x", value="y", confidence=1.0
        )
        assert attr.updated_at is not None


@pytest.mark.django_db
class TestForeignKeyEnforcement:
    """Verify that FK constraints are enforced at the DB level for PersonAttribute."""

    def test_fk_violation_raises_integrity_error(self):
        """Inserting a PersonAttribute with a non-existent person_id raises IntegrityError."""
        bogus_person_id = str(ULID())
        with pytest.raises(IntegrityError):
            PersonAttribute.objects.create(
                person_id=bogus_person_id,
                value_type="text",
                value="hello",
            )


@pytest.mark.django_db
class TestPersonNameConfidenceProvenance:
    """Tests for confidence and provenance fields on PersonName (issue #16)."""

    def _make_person_name(self, person, **kwargs):
        defaults = {
            "name_type": "alias",
            "full_name": "Jane Doe",
            "is_primary": False,
            "source": "manual",
        }
        defaults.update(kwargs)
        return PersonName.objects.create(person=person, **defaults)

    def test_confidence_nullable_by_default(self):
        """confidence defaults to null for manually-entered names."""
        person = Person.objects.create(name="Jane Doe")
        pn = self._make_person_name(person)
        pn.refresh_from_db()
        assert pn.confidence is None

    def test_confidence_accepts_valid_range(self):
        """confidence accepts values in [0.0, 1.0]."""
        person = Person.objects.create(name="Jane Doe")
        pn = self._make_person_name(person, confidence=0.75)
        pn.refresh_from_db()
        assert pn.confidence == 0.75

    def test_confidence_accepts_zero_and_one(self):
        """confidence accepts boundary values 0.0 and 1.0."""
        person = Person.objects.create(name="Jane Doe")
        pn0 = self._make_person_name(person, confidence=0.0)
        pn1 = self._make_person_name(person, full_name="Jane D.", confidence=1.0)
        pn0.refresh_from_db()
        pn1.refresh_from_db()
        assert pn0.confidence == 0.0
        assert pn1.confidence == 1.0

    def test_confidence_rejects_below_zero(self):
        """confidence below 0.0 fails full_clean validation."""
        person = Person.objects.create(name="Jane Doe")
        pn = self._make_person_name(person, confidence=-0.1)
        with pytest.raises(ValidationError):
            pn.full_clean()

    def test_confidence_rejects_above_one(self):
        """confidence above 1.0 fails full_clean validation."""
        person = Person.objects.create(name="Jane Doe")
        pn = self._make_person_name(person, confidence=1.1)
        with pytest.raises(ValidationError):
            pn.full_clean()

    def test_provenance_nullable_by_default(self):
        """provenance defaults to null for manually-entered names."""
        person = Person.objects.create(name="Jane Doe")
        pn = self._make_person_name(person)
        pn.refresh_from_db()
        assert pn.provenance is None

    def test_provenance_stores_json(self):
        """provenance round-trips correctly as a JSONField."""
        person = Person.objects.create(name="Jane Doe")
        payload = {
            "provider": "wikidata",
            "retrieved_at": "2025-07-10T14:00:00Z",
            "wikidata_qid": "Q23",
            "wikidata_alias_lang": "en",
            "source_url": "https://www.wikidata.org/wiki/Q23",
        }
        pn = self._make_person_name(person, provenance=payload)
        pn.refresh_from_db()
        assert pn.provenance == payload

    def test_both_fields_null_for_manual_entry(self):
        """Both confidence and provenance are null for manual entries."""
        person = Person.objects.create(name="Jane Doe")
        pn = self._make_person_name(person)
        pn.refresh_from_db()
        assert pn.confidence is None
        assert pn.provenance is None
