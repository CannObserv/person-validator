"""Tests for WikidataCandidateReviewAdmin — list view, change form, and action paths."""

from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.cookie import CookieStorage
from django.test import RequestFactory

from src.web.persons.admin import WikidataCandidateReviewAdmin
from src.web.persons.models import (
    Person,
    PersonAttribute,
    PersonName,
    WikidataCandidateReview,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CANDIDATES = [
    {
        "qid": "Q23",
        "label": "George Washington",
        "description": "1st US president",
        "score": 0.90,
        "wikipedia_url": "https://en.wikipedia.org/wiki/George_Washington",
        "extract": "George Washington was an American military officer.",
        "properties": {
            "birth_date": "1732-02-22",
            "death_date": "1799-12-14",
            "occupations": ["politician", "military officer"],
            "nationality": "United States of America",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/b/b6/Gilbert_Stuart_Williamstown_Portrait_of_George_Washington.jpg",
        },
    },
    {
        "qid": "Q42",
        "label": "Douglas Adams",
        "description": "English author",
        "score": 0.55,
        "wikipedia_url": None,
        "extract": None,
        "properties": {
            "birth_date": "1952-03-11",
            "death_date": "2001-05-11",
            "occupations": ["novelist"],
            "nationality": "United Kingdom",
            "image_url": None,
        },
    },
]

AUTO_LINKED_CANDIDATES = [
    {
        "qid": "Q23",
        "label": "George Washington",
        "description": "1st US president",
        "score": 0.95,
        "wikipedia_url": "https://en.wikipedia.org/wiki/George_Washington",
        "extract": "George Washington was an American military officer.",
        "properties": {
            "birth_date": "1732-02-22",
            "death_date": "1799-12-14",
            "occupations": ["politician"],
            "nationality": "United States of America",
            "image_url": None,
        },
    }
]


def _make_review(person, status="pending", linked_qid="", candidates=None, **kwargs):
    return WikidataCandidateReview.objects.create(
        person=person,
        query_name="George Washington",
        candidates=candidates if candidates is not None else CANDIDATES,
        status=status,
        linked_qid=linked_qid,
        **kwargs,
    )


def _make_admin(user=None):
    admin = WikidataCandidateReviewAdmin(WikidataCandidateReview, AdminSite())
    return admin


@pytest.fixture()
def superuser(db):
    return User.objects.create_superuser("admin", "admin@example.com", "password")


@pytest.fixture()
def rf():
    return RequestFactory()


# ---------------------------------------------------------------------------
# Admin registration
# ---------------------------------------------------------------------------


class TestWikidataCandidateReviewAdminConfig:
    """WikidataCandidateReviewAdmin is registered and configured correctly."""

    def test_list_display_fields(self):
        """list_display includes required columns."""
        admin = _make_admin()
        for field in (
            "person_link",
            "query_name",
            "review_type",
            "candidate_count",
            "status",
            "linked_qid",
            "reviewed_by",
            "created_at",
        ):
            assert field in admin.list_display

    def test_list_filter(self):
        """list_filter includes status."""
        admin = _make_admin()
        assert "status" in admin.list_filter

    def test_search_fields(self):
        """search_fields includes person name, query_name, linked_qid."""
        admin = _make_admin()
        assert "person__name" in admin.search_fields
        assert "query_name" in admin.search_fields
        assert "linked_qid" in admin.search_fields

    def test_readonly_fields(self):
        """Key fields are read-only."""
        admin = _make_admin()
        for field in ("id", "person", "query_name", "candidates", "reviewed_by", "reviewed_at"):
            assert field in admin.readonly_fields

    def test_change_form_template(self):
        """change_form_template points to the custom template path."""
        admin = _make_admin()
        assert (
            admin.change_form_template == "admin/persons/wikidatacandidatereview/change_form.html"
        )


# ---------------------------------------------------------------------------
# Custom methods: candidate_count, review_type, person_link
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdminHelperMethods:
    """Tests for custom list_display helper methods."""

    def test_candidate_count_multiple(self):
        person = Person.objects.create(name="George Washington")
        review = _make_review(person, candidates=CANDIDATES)
        admin = _make_admin()
        assert admin.candidate_count(review) == 2

    def test_candidate_count_single(self):
        person = Person.objects.create(name="George Washington")
        review = _make_review(person, candidates=AUTO_LINKED_CANDIDATES)
        admin = _make_admin()
        assert admin.candidate_count(review) == 1

    def test_candidate_count_empty(self):
        person = Person.objects.create(name="George Washington")
        review = _make_review(person, candidates=[])
        admin = _make_admin()
        assert admin.candidate_count(review) == 0

    def test_review_type_pending(self):
        person = Person.objects.create(name="George Washington")
        review = _make_review(person, status="pending")
        admin = _make_admin()
        output = str(admin.review_type(review))
        assert "Ambiguous" in output

    def test_review_type_auto_linked(self):
        person = Person.objects.create(name="George Washington")
        review = _make_review(person, status="auto_linked", candidates=AUTO_LINKED_CANDIDATES)
        admin = _make_admin()
        output = str(admin.review_type(review))
        assert "Auto-linked" in output

    def test_person_link_renders_anchor(self):
        person = Person.objects.create(name="George Washington")
        review = _make_review(person)
        admin = _make_admin()
        output = str(admin.person_link(review))
        assert "<a" in output
        assert "George Washington" in output


# ---------------------------------------------------------------------------
# get_queryset default filter
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGetQuerysetDefaultFilter:
    """Default queryset shows only actionable (pending + auto_linked) reviews."""

    def test_default_shows_actionable(self, superuser, rf):
        person = Person.objects.create(name="George Washington")
        pending = _make_review(person, status="pending")
        auto = _make_review(person, status="auto_linked", candidates=AUTO_LINKED_CANDIDATES)
        accepted = _make_review(person, status="accepted", linked_qid="Q23")

        request = rf.get("/admin/persons/wikidatacandidatereview/")
        request.user = superuser
        admin = _make_admin()
        qs = admin.get_queryset(request)
        pks = list(qs.values_list("pk", flat=True))
        assert str(pending.pk) in pks
        assert str(auto.pk) in pks
        assert str(accepted.pk) not in pks

    def test_custom_status_filter_bypasses_default(self, superuser, rf):
        """Passing status__in in GET params bypasses the default filter."""
        person = Person.objects.create(name="George Washington")
        accepted = _make_review(person, status="accepted", linked_qid="Q23")

        request = rf.get(
            "/admin/persons/wikidatacandidatereview/",
            {"status": "accepted"},
        )
        request.user = superuser
        admin = _make_admin()
        qs = admin.get_queryset(request)
        pks = list(qs.values_list("pk", flat=True))
        assert str(accepted.pk) in pks


# ---------------------------------------------------------------------------
# response_change: Mode A — pending accept
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestResponseChangeAccept:
    """Mode A: admin accepts a pending review by selecting a candidate."""

    def test_accept_sets_status_and_qid(self, superuser, rf):
        person = Person.objects.create(name="George Washington")
        review = _make_review(person, status="pending")

        request = rf.post(
            f"/admin/persons/wikidatacandidatereview/{review.pk}/change/",
            {"_action": "accept", "linked_qid": "Q23"},
        )
        request.user = superuser
        request._messages = CookieStorage(request)

        admin = _make_admin()
        with patch("src.web.persons.review_handlers.run_enrichment_for_person"):
            admin.response_change(request, review)

        review.refresh_from_db()
        assert review.status == "accepted"
        assert review.linked_qid == "Q23"
        assert review.reviewed_by == superuser
        assert review.reviewed_at is not None

    def test_accept_invalid_qid_returns_form_error(self, superuser, rf):
        """Submitting a QID not in candidates raises a validation error."""
        person = Person.objects.create(name="George Washington")
        review = _make_review(person, status="pending")

        request = rf.post(
            f"/admin/persons/wikidatacandidatereview/{review.pk}/change/",
            {"_action": "accept", "linked_qid": "Q9999"},
        )
        request.user = superuser

        request._messages = CookieStorage(request)

        admin = _make_admin()
        admin.response_change(request, review)

        review.refresh_from_db()
        assert review.status == "pending"

    def test_accept_missing_qid_returns_form_error(self, superuser, rf):
        """Submitting accept with no linked_qid raises a validation error."""
        person = Person.objects.create(name="George Washington")
        review = _make_review(person, status="pending")

        request = rf.post(
            f"/admin/persons/wikidatacandidatereview/{review.pk}/change/",
            {"_action": "accept"},
        )
        request.user = superuser

        request._messages = CookieStorage(request)

        admin = _make_admin()
        admin.response_change(request, review)

        review.refresh_from_db()
        assert review.status == "pending"


# ---------------------------------------------------------------------------
# response_change: Mode A — reject / skip
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestResponseChangeRejectSkip:
    """Mode A: admin rejects or skips a pending review."""

    def test_reject_pending_sets_status(self, superuser, rf):
        person = Person.objects.create(name="George Washington")
        review = _make_review(person, status="pending")

        request = rf.post(
            f"/admin/persons/wikidatacandidatereview/{review.pk}/change/",
            {"_action": "reject"},
        )
        request.user = superuser

        request._messages = CookieStorage(request)

        admin = _make_admin()
        admin.response_change(request, review)

        review.refresh_from_db()
        assert review.status == "rejected"
        assert review.reviewed_by == superuser
        assert review.reviewed_at is not None

    def test_skip_sets_status(self, superuser, rf):
        person = Person.objects.create(name="George Washington")
        review = _make_review(person, status="pending")

        request = rf.post(
            f"/admin/persons/wikidatacandidatereview/{review.pk}/change/",
            {"_action": "skip"},
        )
        request.user = superuser

        request._messages = CookieStorage(request)

        admin = _make_admin()
        admin.response_change(request, review)

        review.refresh_from_db()
        assert review.status == "skipped"
        assert review.reviewed_by == superuser
        assert review.reviewed_at is not None


# ---------------------------------------------------------------------------
# response_change: Mode B — auto_linked confirm
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestResponseChangeConfirm:
    """Mode B: admin confirms an auto_linked review."""

    def test_confirm_sets_status_and_calls_bump(self, superuser, rf):
        person = Person.objects.create(name="George Washington")
        review = _make_review(
            person,
            status="auto_linked",
            linked_qid="Q23",
            candidates=AUTO_LINKED_CANDIDATES,
        )

        request = rf.post(
            f"/admin/persons/wikidatacandidatereview/{review.pk}/change/",
            {"_action": "confirm"},
        )
        request.user = superuser

        request._messages = CookieStorage(request)

        admin = _make_admin()
        with patch("src.web.persons.review_handlers.bump_wikidata_confidence"):
            admin.response_change(request, review)

        review.refresh_from_db()
        assert review.status == "confirmed"
        assert review.reviewed_by == superuser
        assert review.reviewed_at is not None


# ---------------------------------------------------------------------------
# response_change: Mode B — auto_linked reject (rollback)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestResponseChangeAutoLinkedReject:
    """Mode B: rejecting an auto_linked review calls rollback directly."""

    def test_reject_auto_linked_calls_rollback(self, superuser, rf):
        person = Person.objects.create(name="George Washington")
        # Create an attribute that should be rolled back
        PersonAttribute.objects.create(
            person=person,
            key="wikidata_qid",
            value="Q23",
            value_type="text",
            source="wikidata",
            confidence=0.75,
        )
        review = _make_review(
            person,
            status="auto_linked",
            linked_qid="Q23",
            candidates=AUTO_LINKED_CANDIDATES,
        )

        request = rf.post(
            f"/admin/persons/wikidatacandidatereview/{review.pk}/change/",
            {"_action": "reject"},
        )
        request.user = superuser

        request._messages = CookieStorage(request)

        admin = _make_admin()
        with patch("src.web.persons.admin.rollback_wikidata_autolink") as mock_rollback:
            admin.response_change(request, review)
            mock_rollback.assert_called_once_with(person_id=str(person.pk))

        review.refresh_from_db()
        assert review.status == "rejected"
        assert review.reviewed_by == superuser
        assert review.reviewed_at is not None


# ---------------------------------------------------------------------------
# rollback_wikidata_autolink task
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRollbackWikidataAutolink:
    """rollback_wikidata_autolink deletes wikidata attributes at 0.75 confidence."""

    def test_deletes_auto_linked_attributes(self):
        from src.core.enrichment.tasks import rollback_wikidata_autolink

        person = Person.objects.create(name="George Washington")
        attr = PersonAttribute.objects.create(
            person=person,
            key="wikidata_qid",
            value="Q23",
            value_type="text",
            source="wikidata",
            confidence=0.75,
        )
        rollback_wikidata_autolink(person_id=str(person.pk))
        assert not PersonAttribute.objects.filter(pk=attr.pk).exists()

    def test_does_not_delete_high_confidence_attributes(self):
        from src.core.enrichment.tasks import rollback_wikidata_autolink

        person = Person.objects.create(name="George Washington")
        attr = PersonAttribute.objects.create(
            person=person,
            key="wikidata_qid",
            value="Q23",
            value_type="text",
            source="wikidata",
            confidence=0.95,
        )
        rollback_wikidata_autolink(person_id=str(person.pk))
        assert PersonAttribute.objects.filter(pk=attr.pk).exists()

    def test_does_not_delete_non_wikidata_attributes(self):
        from src.core.enrichment.tasks import rollback_wikidata_autolink

        person = Person.objects.create(name="George Washington")
        attr = PersonAttribute.objects.create(
            person=person,
            key="some_key",
            value="val",
            value_type="text",
            source="manual",
            confidence=0.75,
        )
        rollback_wikidata_autolink(person_id=str(person.pk))
        assert PersonAttribute.objects.filter(pk=attr.pk).exists()

    def test_deletes_auto_linked_person_names(self):
        from src.core.enrichment.tasks import rollback_wikidata_autolink

        person = Person.objects.create(name="George Washington")
        name = PersonName.objects.create(
            person=person,
            full_name="Geo. Washington",
            name_type="alias",
            source="wikidata",
            confidence=0.70,
        )
        rollback_wikidata_autolink(person_id=str(person.pk))
        assert not PersonName.objects.filter(pk=name.pk).exists()

    def test_does_not_delete_high_confidence_names(self):
        from src.core.enrichment.tasks import rollback_wikidata_autolink

        person = Person.objects.create(name="George Washington")
        name = PersonName.objects.create(
            person=person,
            full_name="George Washington",
            name_type="alias",
            source="wikidata",
            confidence=0.80,
        )
        rollback_wikidata_autolink(person_id=str(person.pk))
        assert PersonName.objects.filter(pk=name.pk).exists()

    def test_re_enqueues_for_manual_search(self):
        """rollback_wikidata_autolink re-triggers enrichment for fresh search."""
        from src.core.enrichment.tasks import rollback_wikidata_autolink

        person = Person.objects.create(name="George Washington")
        with patch("src.core.enrichment.tasks.run_enrichment_for_person") as mock_run:
            rollback_wikidata_autolink(person_id=str(person.pk))
            mock_run.assert_called_once_with(
                person_id=str(person.pk),
                triggered_by="rollback",
                force_rescore=True,
            )
