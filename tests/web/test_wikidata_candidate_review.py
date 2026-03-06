"""Tests for WikidataCandidateReview model, post-save signal, and enrichment tasks."""

from unittest.mock import patch

import pytest

from src.web.persons.models import (
    Person,
    WikidataCandidateReview,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CANDIDATES = [
    {
        "qid": "Q23",
        "label": "George Washington",
        "description": "1st US president",
        "score": 0.85,
        "wikipedia_url": "https://en.wikipedia.org/wiki/George_Washington",
        "extract": None,
        "properties": {
            "birth_date": "1732-02-22",
            "death_date": "1799-12-14",
            "occupations": ["politician"],
            "nationality": "United States of America",
            "image_url": None,
        },
    }
]


def _make_review(person, status="pending", linked_qid="", **kwargs):
    return WikidataCandidateReview.objects.create(
        person=person,
        query_name="George Washington",
        candidates=CANDIDATES,
        status=status,
        linked_qid=linked_qid,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Model structure
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWikidataCandidateReviewModel:
    """Tests for the WikidataCandidateReview model structure and DB table."""

    def test_table_name(self):
        """Maps to persons_wikidatacandidatereview table."""
        assert WikidataCandidateReview._meta.db_table == "persons_wikidatacandidatereview"

    def test_create_review(self):
        """A WikidataCandidateReview can be created."""
        person = Person.objects.create(name="George Washington")
        review = _make_review(person)
        assert review.pk is not None
        assert len(review.pk) == 26  # ULID
        assert review.status == "pending"
        assert review.linked_qid == ""

    def test_pk_is_ulid(self):
        """Primary key is a 26-char ULID string."""
        from src.core.fields import ULIDField

        field = WikidataCandidateReview._meta.get_field("id")
        assert isinstance(field, ULIDField)
        assert field.primary_key is True

    def test_status_choices_include_auto_linked_and_confirmed(self):
        """STATUS_CHOICES includes auto_linked and confirmed."""
        choices = {k for k, _ in WikidataCandidateReview.STATUS_CHOICES}
        assert "auto_linked" in choices
        assert "confirmed" in choices
        assert "accepted" in choices
        assert "pending" in choices
        assert "rejected" in choices
        assert "skipped" in choices

    def test_str_representation(self):
        """__str__ includes person name and status."""
        person = Person.objects.create(name="George Washington")
        review = _make_review(person)
        s = str(review)
        assert "George Washington" in s
        assert "pending" in s

    def test_cascade_delete(self):
        """Deleting a Person also deletes related reviews."""
        person = Person.objects.create(name="George Washington")
        _make_review(person)
        person.delete()
        assert WikidataCandidateReview.objects.count() == 0

    def test_reviewed_by_nullable(self):
        """reviewed_by and reviewed_at are nullable."""
        person = Person.objects.create(name="George Washington")
        review = _make_review(person)
        assert review.reviewed_by is None
        assert review.reviewed_at is None

    def test_indexes_exist(self):
        """Both required indexes are defined."""
        index_fields = [tuple(idx.fields) for idx in WikidataCandidateReview._meta.indexes]
        assert ("status", "-created_at") in index_fields
        assert ("person", "status") in index_fields


# ---------------------------------------------------------------------------
# Signal: does not fire on create
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestReviewSignalNoFireOnCreate:
    """Signal does not invoke task helpers when a review is first created."""

    def test_signal_does_not_fire_on_create(self):
        """post_save created=True guard prevents dispatch even for actionable statuses."""
        person = Person.objects.create(name="George Washington")
        with patch("src.web.persons.review_handlers.handle_accepted") as mock_accepted:
            _make_review(person, status="accepted", linked_qid="Q23")
            mock_accepted.assert_not_called()


# ---------------------------------------------------------------------------
# Signal: accepted -> run_enrichment_for_person
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestReviewSignalAccepted:
    """Signal dispatches handle_accepted when status transitions to accepted."""

    def test_signal_fires_on_accepted(self):
        person = Person.objects.create(name="George Washington")
        review = _make_review(person, status="pending")

        with patch("src.web.persons.review_handlers.run_enrichment_for_person") as mock_run:
            review.status = "accepted"
            review.linked_qid = "Q23"
            review.save()

            mock_run.assert_called_once_with(
                person_id=str(person.pk),
                triggered_by="adjudication",
                confirmed_wikidata_qid="Q23",
            )

    def test_signal_does_not_fire_accepted_without_qid(self):
        """If linked_qid is blank, run_enrichment_for_person is NOT called."""
        person = Person.objects.create(name="George Washington")
        review = _make_review(person, status="pending")

        with patch("src.web.persons.review_handlers.run_enrichment_for_person") as mock_run:
            review.status = "accepted"
            review.linked_qid = ""
            review.save()

            mock_run.assert_not_called()

    def test_signal_does_not_refire_on_unrelated_save(self):
        """Saving an already-accepted review without changing status does not re-dispatch."""
        person = Person.objects.create(name="George Washington")
        review = _make_review(person, status="accepted", linked_qid="Q23")

        with patch("src.web.persons.review_handlers.run_enrichment_for_person") as mock_run:
            # Simulate an unrelated field update (e.g. admin sets reviewed_at)
            review.reviewed_at = review.created_at
            review.save()
            mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Signal: confirmed -> bump_wikidata_confidence
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestReviewSignalConfirmed:
    """Signal dispatches handle_confirmed when status transitions to confirmed."""

    def test_signal_fires_on_confirmed(self):
        person = Person.objects.create(name="George Washington")
        review = _make_review(person, status="auto_linked", linked_qid="Q23")

        with (
            patch("src.web.persons.review_handlers.run_enrichment_for_person") as mock_run,
            patch("src.web.persons.review_handlers.bump_wikidata_confidence") as mock_bump,
        ):
            review.status = "confirmed"
            review.save()

            mock_bump.assert_called_once_with(
                person_id=str(person.pk),
                reviewed_by_id=None,
            )
            mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Signal: other status transitions do NOT fire tasks
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestReviewSignalOtherStatuses:
    """Signal does not invoke handlers for statuses not in DISPATCH."""

    @pytest.mark.parametrize("new_status", ["rejected", "skipped"])
    def test_signal_does_not_fire_for_status(self, new_status):
        person = Person.objects.create(name="George Washington")
        review = _make_review(person, status="pending")

        with (
            patch("src.web.persons.review_handlers.run_enrichment_for_person") as mock_run,
            patch("src.web.persons.review_handlers.bump_wikidata_confidence") as mock_bump,
        ):
            review.status = new_status
            review.save()

            mock_run.assert_not_called()
            mock_bump.assert_not_called()


# ---------------------------------------------------------------------------
# Tasks: run_enrichment_for_person
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRunEnrichmentForPerson:
    """Tests for the run_enrichment_for_person task utility."""

    def test_raises_if_person_not_found(self):
        """DoesNotExist raised for unknown person_id."""
        from src.core.enrichment.tasks import run_enrichment_for_person

        with pytest.raises(Person.DoesNotExist):
            run_enrichment_for_person(
                person_id="DOESNOTEXIST000000000000000",
                triggered_by="manual",
            )

    def test_runs_against_person(self):
        """Calls EnrichmentRunner.run with a PersonData built from the Person record."""
        from src.core.enrichment.tasks import run_enrichment_for_person

        person = Person.objects.create(
            name="George Washington",
            given_name="George",
            surname="Washington",
        )

        with patch("src.core.enrichment.runner.EnrichmentRunner.run") as mock_run:
            run_enrichment_for_person(
                person_id=str(person.pk),
                triggered_by="adjudication",
            )
            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args
            person_data = call_kwargs.args[0]
            assert person_data.id == str(person.pk)
            assert person_data.name == "George Washington"
            assert person_data.given_name == "George"
            assert person_data.surname == "Washington"
            assert call_kwargs.kwargs["triggered_by"] == "adjudication"

    def test_injects_confirmed_qid_into_existing_attributes(self):
        """confirmed_wikidata_qid is injected as a synthetic attribute."""
        from src.core.enrichment.tasks import run_enrichment_for_person

        person = Person.objects.create(name="George Washington")

        with patch("src.core.enrichment.runner.EnrichmentRunner.run") as mock_run:
            run_enrichment_for_person(
                person_id=str(person.pk),
                triggered_by="adjudication",
                confirmed_wikidata_qid="Q23",
            )
            person_data = mock_run.call_args.args[0]
            qid_attrs = [a for a in person_data.existing_attributes if a["key"] == "wikidata_qid"]
            assert len(qid_attrs) == 1
            assert qid_attrs[0]["value"] == "Q23"

    def test_confirmed_qid_replaces_existing_wikidata_qid(self):
        """If wikidata_qid already exists, it is replaced by confirmed_wikidata_qid."""
        from src.core.enrichment.tasks import run_enrichment_for_person

        person = Person.objects.create(name="George Washington")

        # Patch _load_existing_attributes to return a pre-existing wikidata_qid.
        stale = [
            {"key": "wikidata_qid", "value": "Q999", "value_type": "text", "source": "wikidata"}
        ]
        with (
            patch("src.core.enrichment.runner._load_existing_attributes", return_value=stale),
            patch("src.core.enrichment.runner.EnrichmentRunner.run") as mock_run,
        ):
            run_enrichment_for_person(
                person_id=str(person.pk),
                triggered_by="adjudication",
                confirmed_wikidata_qid="Q23",
            )
            person_data = mock_run.call_args.args[0]
            qid_attrs = [a for a in person_data.existing_attributes if a["key"] == "wikidata_qid"]
            assert len(qid_attrs) == 1
            assert qid_attrs[0]["value"] == "Q23"


# ---------------------------------------------------------------------------
# Tasks: bump_wikidata_confidence
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBumpWikidataConfidence:
    """Tests for the bump_wikidata_confidence task utility."""

    def test_bumps_matching_attributes(self):
        """Updates confidence 0.75 -> 0.95 for wikidata-sourced attributes."""
        from src.core.enrichment.tasks import bump_wikidata_confidence
        from src.web.persons.models import PersonAttribute

        person = Person.objects.create(name="George Washington")
        attr = PersonAttribute.objects.create(
            person=person,
            key="wikidata_qid",
            value="Q23",
            value_type="text",
            source="wikidata",
            confidence=0.75,
        )

        bump_wikidata_confidence(person_id=str(person.pk), reviewed_by_id=None)

        attr.refresh_from_db()
        assert float(attr.confidence) == pytest.approx(0.95)

    def test_does_not_touch_other_sources(self):
        """Attributes from non-wikidata sources are not updated."""
        from src.core.enrichment.tasks import bump_wikidata_confidence
        from src.web.persons.models import PersonAttribute

        person = Person.objects.create(name="George Washington")
        attr = PersonAttribute.objects.create(
            person=person,
            key="some_key",
            value="val",
            value_type="text",
            source="manual",
            confidence=0.75,
        )

        bump_wikidata_confidence(person_id=str(person.pk), reviewed_by_id=None)

        attr.refresh_from_db()
        assert float(attr.confidence) == pytest.approx(0.75)

    def test_does_not_touch_already_high_confidence(self):
        """Wikidata attributes already at 0.95 are not double-updated."""
        from src.core.enrichment.tasks import bump_wikidata_confidence
        from src.web.persons.models import PersonAttribute

        person = Person.objects.create(name="George Washington")
        attr = PersonAttribute.objects.create(
            person=person,
            key="wikidata_qid",
            value="Q23",
            value_type="text",
            source="wikidata",
            confidence=0.95,
        )

        bump_wikidata_confidence(person_id=str(person.pk), reviewed_by_id=None)

        attr.refresh_from_db()
        assert float(attr.confidence) == pytest.approx(0.95)

    def test_only_updates_given_person(self):
        """Attributes for other persons are not affected."""
        from src.core.enrichment.tasks import bump_wikidata_confidence
        from src.web.persons.models import PersonAttribute

        person1 = Person.objects.create(name="George Washington")
        person2 = Person.objects.create(name="John Adams")
        attr2 = PersonAttribute.objects.create(
            person=person2,
            key="wikidata_qid",
            value="Q11806",
            value_type="text",
            source="wikidata",
            confidence=0.75,
        )

        bump_wikidata_confidence(person_id=str(person1.pk), reviewed_by_id=None)

        attr2.refresh_from_db()
        assert float(attr2.confidence) == pytest.approx(0.75)

    def test_bumps_alias_personname_confidence(self):
        """PersonName rows at 0.70 (alias confidence) are bumped to 0.80."""
        from src.core.enrichment.tasks import bump_wikidata_confidence
        from src.web.persons.models import PersonName

        person = Person.objects.create(name="George Washington")
        name = PersonName.objects.create(
            person=person,
            full_name="Geo. Washington",
            name_type="alias",
            source="wikidata",
            confidence=0.70,
        )

        bump_wikidata_confidence(person_id=str(person.pk), reviewed_by_id=None)

        name.refresh_from_db()
        assert float(name.confidence) == pytest.approx(0.80)

    def test_does_not_bump_personname_from_other_source(self):
        """PersonName rows from non-wikidata sources are not touched."""
        from src.core.enrichment.tasks import bump_wikidata_confidence
        from src.web.persons.models import PersonName

        person = Person.objects.create(name="George Washington")
        name = PersonName.objects.create(
            person=person,
            full_name="George Washington",
            name_type="alias",
            source="manual",
            confidence=0.70,
        )

        bump_wikidata_confidence(person_id=str(person.pk), reviewed_by_id=None)

        name.refresh_from_db()
        assert float(name.confidence) == pytest.approx(0.70)

    def test_does_not_bump_personname_at_high_confidence(self):
        """PersonName rows already at 0.80 are not double-bumped."""
        from src.core.enrichment.tasks import bump_wikidata_confidence
        from src.web.persons.models import PersonName

        person = Person.objects.create(name="George Washington")
        name = PersonName.objects.create(
            person=person,
            full_name="Geo. Washington",
            name_type="alias",
            source="wikidata",
            confidence=0.80,
        )

        bump_wikidata_confidence(person_id=str(person.pk), reviewed_by_id=None)

        name.refresh_from_db()
        assert float(name.confidence) == pytest.approx(0.80)

    def test_idempotent_on_already_confirmed_attributes(self):
        """Calling bump twice does not raise PersonAttribute confidence above 0.95."""
        from src.core.enrichment.tasks import bump_wikidata_confidence
        from src.web.persons.models import PersonAttribute

        person = Person.objects.create(name="George Washington")
        attr = PersonAttribute.objects.create(
            person=person,
            key="wikidata_qid",
            value="Q23",
            value_type="text",
            source="wikidata",
            confidence=0.75,
        )

        bump_wikidata_confidence(person_id=str(person.pk), reviewed_by_id=None)
        bump_wikidata_confidence(person_id=str(person.pk), reviewed_by_id=None)

        attr.refresh_from_db()
        assert float(attr.confidence) == pytest.approx(0.95)

    def test_idempotent_on_already_confirmed_names(self):
        """Calling bump twice does not raise PersonName confidence above 0.80."""
        from src.core.enrichment.tasks import bump_wikidata_confidence
        from src.web.persons.models import PersonName

        person = Person.objects.create(name="George Washington")
        name = PersonName.objects.create(
            person=person,
            full_name="Geo. Washington",
            name_type="alias",
            source="wikidata",
            confidence=0.70,
        )

        bump_wikidata_confidence(person_id=str(person.pk), reviewed_by_id=None)
        bump_wikidata_confidence(person_id=str(person.pk), reviewed_by_id=None)

        name.refresh_from_db()
        assert float(name.confidence) == pytest.approx(0.80)
