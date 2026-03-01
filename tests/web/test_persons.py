"""Tests for Person and PersonName models."""

import pytest
from django.db import IntegrityError

from src.core.fields import ULIDField
from src.web.persons.models import NAME_TYPE_CHOICES, Person, PersonName


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
        from django.db import connection

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
