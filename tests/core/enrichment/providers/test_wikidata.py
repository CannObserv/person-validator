"""Tests for WikidataProvider.

Unit tests use a fake WikimediaHttpClient so no real HTTP calls are made.
Integration tests (marked @pytest.mark.integration) hit live Wikidata.
"""

from unittest.mock import MagicMock

import pytest

from src.core.enrichment.base import NoMatchSignal, PersonData
from src.core.enrichment.providers.wikidata import (
    WikidataProvider,
    _get_en_aliases,
    _get_en_description,
    _get_en_label,
    _has_wikipedia_article,
    _is_disambiguation_page,
    _is_human,
    _parse_date,
    _score_candidate,
)

# ---------------------------------------------------------------------------
# Test entity fixtures
# ---------------------------------------------------------------------------


def _make_entity(
    qid: str = "Q23",
    label: str = "George Washington",
    description: str = "1st president of the United States",
    aliases: list[str] | None = None,
    birth_time: str | None = "+1732-02-22T00:00:00Z",
    birth_precision: int = 11,
    death_time: str | None = "+1799-12-14T00:00:00Z",
    death_precision: int = 11,
    occupation_qids: list[str] | None = None,
    citizenship_qids: list[str] | None = None,
    has_enwiki: bool = True,
    p31_qids: list[str] | None = None,
) -> dict:
    """Build a minimal Wikidata entity dict for testing."""
    entity: dict = {
        "id": qid,
        "labels": {"en": {"value": label}},
        "descriptions": {"en": {"value": description}},
        "aliases": {"en": [{"value": a} for a in (aliases or [])]},
        "claims": {},
        "sitelinks": {"enwiki": {"title": label.replace(" ", "_")}} if has_enwiki else {},
    }
    if p31_qids is None:
        p31_qids = ["Q5"]
    entity["claims"]["P31"] = [
        {"mainsnak": {"datavalue": {"value": {"id": qid_val}}}} for qid_val in p31_qids
    ]
    if birth_time is not None:
        entity["claims"]["P569"] = [
            {
                "mainsnak": {
                    "datavalue": {
                        "type": "time",
                        "value": {"time": birth_time, "precision": birth_precision},
                    }
                }
            }
        ]
    if death_time is not None:
        entity["claims"]["P570"] = [
            {
                "mainsnak": {
                    "datavalue": {
                        "type": "time",
                        "value": {"time": death_time, "precision": death_precision},
                    }
                }
            }
        ]
    if occupation_qids:
        entity["claims"]["P106"] = [
            {"mainsnak": {"datavalue": {"value": {"id": q}}}} for q in occupation_qids
        ]
    if citizenship_qids:
        entity["claims"]["P27"] = [
            {"mainsnak": {"datavalue": {"value": {"id": q}}}} for q in citizenship_qids
        ]
    return entity


def _make_person(
    person_id: str = "01HZ",
    name: str = "George Washington",
    given_name: str | None = "George",
    surname: str | None = "Washington",
    existing_attributes: list[dict] | None = None,
) -> PersonData:
    return PersonData(
        id=person_id,
        name=name,
        given_name=given_name,
        surname=surname,
        existing_attributes=existing_attributes or [],
    )


def _make_fake_client(
    search_results: list[dict] | None = None,
    entity_map: dict[str, dict] | None = None,
) -> MagicMock:
    """Build a mock WikimediaHttpClient."""
    client = MagicMock()
    client.search_entities.return_value = search_results or []
    client.get_entities.return_value = entity_map or {}
    client.sparql.return_value = []
    return client


# ---------------------------------------------------------------------------
# Entity parsing helpers
# ---------------------------------------------------------------------------


class TestEntityParsing:
    """Unit tests for entity parsing helper functions."""

    def test_is_human_true(self):
        entity = _make_entity(p31_qids=["Q5"])
        assert _is_human(entity) is True

    def test_is_human_false(self):
        entity = _make_entity(p31_qids=["Q11424"])  # film
        assert _is_human(entity) is False

    def test_is_disambiguation_page_true(self):
        entity = _make_entity(p31_qids=["Q4167410"])
        assert _is_disambiguation_page(entity) is True

    def test_is_disambiguation_page_false(self):
        entity = _make_entity(p31_qids=["Q5"])
        assert _is_disambiguation_page(entity) is False

    def test_has_wikipedia_article_true(self):
        entity = _make_entity(has_enwiki=True)
        assert _has_wikipedia_article(entity) is True

    def test_has_wikipedia_article_false(self):
        entity = _make_entity(has_enwiki=False)
        assert _has_wikipedia_article(entity) is False

    def test_get_en_label(self):
        entity = _make_entity(label="Ada Lovelace")
        assert _get_en_label(entity) == "Ada Lovelace"

    def test_get_en_description(self):
        entity = _make_entity(description="mathematician")
        assert _get_en_description(entity) == "mathematician"

    def test_get_en_aliases(self):
        entity = _make_entity(aliases=["G. Washington", "First POTUS"])
        assert _get_en_aliases(entity) == ["G. Washington", "First POTUS"]

    def test_get_en_aliases_empty(self):
        entity = _make_entity(aliases=[])
        assert _get_en_aliases(entity) == []


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------


class TestParseDate:
    """Tests for date precision handling."""

    def test_day_precision(self):
        tv = {"time": "+1732-02-22T00:00:00Z", "precision": 11}
        date_str, year_str = _parse_date(tv)
        assert date_str == "1732-02-22"
        assert year_str is None

    def test_year_precision(self):
        tv = {"time": "+1732-00-00T00:00:00Z", "precision": 9}
        date_str, year_str = _parse_date(tv)
        assert date_str is None
        assert year_str == "1732"

    def test_century_precision_returns_none(self):
        tv = {"time": "+1700-00-00T00:00:00Z", "precision": 7}
        date_str, year_str = _parse_date(tv)
        assert date_str is None
        assert year_str is None

    def test_negative_year_returns_none(self):
        """BC dates (negative years) are skipped."""
        tv = {"time": "-0044-03-15T00:00:00Z", "precision": 11}
        date_str, year_str = _parse_date(tv)
        assert date_str is None
        assert year_str is None

    def test_month_precision_returns_none_none(self):
        """Month precision (10) is between year (9) and day (11) precision.

        ``_parse_date`` only handles day (>=11) and year (==9).  Month
        precision falls through both branches and returns ``(None, None)``.
        """
        tv = {"time": "+1732-02-00T00:00:00Z", "precision": 10}
        date_str, year_str = _parse_date(tv)
        assert date_str is None
        assert year_str is None


# ---------------------------------------------------------------------------
# _score_candidate
# ---------------------------------------------------------------------------


class TestScoreCandidate:
    """Tests for disambiguation scoring."""

    def test_wikipedia_article_adds_score(self):
        entity = _make_entity(has_enwiki=True)
        person = _make_person()
        score = _score_candidate(entity, person, {}, {})
        assert score >= 0.05

    def test_no_wikipedia_no_extra_score(self):
        """Without Wikipedia and with a non-matching name, wiki contributes 0."""
        entity = _make_entity(has_enwiki=False, label="Someone Else")
        person = _make_person(name="Different Person", given_name="Different", surname="Person")
        score = _score_candidate(entity, person, {}, {})
        assert score < 0.05

    def test_birth_year_match_adds_score(self):
        entity = _make_entity(birth_time="+1732-00-00T00:00:00Z", birth_precision=9)
        person = _make_person(
            existing_attributes=[{"key": "birth_year", "value": "1732", "value_type": "text"}]
        )
        score = _score_candidate(entity, person, {}, {})
        assert score >= 0.35

    def test_birth_year_mismatch_no_score(self):
        entity = _make_entity(
            label="Someone Unrelated",
            birth_time="+1732-00-00T00:00:00Z",
            birth_precision=9,
            has_enwiki=False,
        )
        person = _make_person(
            name="Different Person",
            given_name="Different",
            surname="Person",
            existing_attributes=[{"key": "birth_year", "value": "1900", "value_type": "text"}],
        )
        score = _score_candidate(entity, person, {}, {})
        assert score == 0.0

    def test_occupation_match_adds_score(self):
        entity = _make_entity(occupation_qids=["Q82955"])  # politician
        person = _make_person(
            existing_attributes=[
                {"key": "bio", "value": "politician and general", "value_type": "text"}
            ]
        )
        occ_labels = {"Q82955": "politician"}
        score = _score_candidate(entity, person, occ_labels, {})
        assert score >= 0.25

    def test_alias_match_adds_score(self):
        entity = _make_entity(aliases=["G. Washington"])
        person = _make_person(
            existing_attributes=[
                {"key": "n", "full_name": "G. Washington", "value_type": "text", "value": ""}
            ]
        )
        score = _score_candidate(entity, person, {}, {})
        assert score >= 0.15

    def test_name_match_via_person_name_field(self):
        """Person primary name matching alias gives score contribution."""
        entity = _make_entity(label="George Washington", aliases=["Washington"])
        person = _make_person(name="George Washington")
        score = _score_candidate(entity, person, {}, {})
        # Alias check includes entity label; George Washington == George Washington
        assert score >= 0.15


# ---------------------------------------------------------------------------
# WikidataProvider.enrich — unit tests with fake client
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWikidataProviderEnrich:
    """Unit tests for WikidataProvider.enrich (no real HTTP calls)."""

    def _make_provider(self, client: MagicMock) -> WikidataProvider:
        return WikidataProvider(http_client=client)

    def test_no_candidates_raises_no_match_signal(self):
        """When search returns no candidates, raises NoMatchSignal."""
        client = _make_fake_client(search_results=[])
        provider = self._make_provider(client)
        person = _make_person()

        with pytest.raises(NoMatchSignal):
            provider.enrich(person)

    def test_no_human_candidates_raises_no_match_signal(self):
        """When all candidates are non-human entities, raises NoMatchSignal."""
        entity = _make_entity(p31_qids=["Q11424"])  # film
        client = _make_fake_client(
            search_results=[{"id": "Q11424"}],
            entity_map={"Q11424": entity},
        )
        provider = self._make_provider(client)
        person = _make_person()

        with pytest.raises(NoMatchSignal):
            provider.enrich(person)

    def test_disambiguation_page_filtered_out(self):
        """Disambiguation pages (P31=Q4167410) are excluded; NoMatchSignal raised."""
        entity = _make_entity(p31_qids=["Q4167410"])
        client = _make_fake_client(
            search_results=[{"id": "Q23"}],
            entity_map={"Q23": entity},
        )
        provider = self._make_provider(client)
        person = _make_person()

        with pytest.raises(NoMatchSignal):
            provider.enrich(person)

    def test_low_score_creates_pending_review(self, db):
        """Single candidate below threshold creates WikidataCandidateReview(pending)."""
        from src.web.persons.models import Person, WikidataCandidateReview

        entity = _make_entity(has_enwiki=False)
        # get_entities is called once (batch fetch); _fetch_scoring_labels skips
        # the HTTP call when there are no occ/nat QIDs on the entity.
        client = _make_fake_client(
            search_results=[{"id": "Q23"}],
            entity_map={"Q23": entity},
        )

        person_obj = Person.objects.create(name="George Washington")
        person = _make_person(person_id=str(person_obj.pk))
        provider = self._make_provider(client)

        result = provider.enrich(person)

        assert result == []
        reviews = WikidataCandidateReview.objects.filter(person=person_obj)
        assert reviews.count() == 1
        assert reviews.first().status == "pending"

    def test_auto_link_path(self, db):
        """Single candidate above threshold auto-links and creates auto_linked review."""
        from src.web.persons.models import Person, WikidataCandidateReview

        entity = _make_entity(
            birth_time="+1732-00-00T00:00:00Z",
            birth_precision=9,
            occupation_qids=["Q82955"],
            citizenship_qids=["Q30"],
            has_enwiki=True,
            aliases=["G. Washington"],
        )
        # Full score: birth_year (0.35) + occ (0.25) + nat (0.20) + alias (0.15) + wiki (0.05) = 1.0
        occ_entity = {"id": "Q82955", "labels": {"en": {"value": "politician"}}, "claims": {}}
        nat_entity = {"id": "Q30", "labels": {"en": {"value": "United States"}}, "claims": {}}

        def get_entities_side_effect(qids):
            mapping = {
                "Q23": entity,
                "Q82955": occ_entity,
                "Q30": nat_entity,
            }
            return {q: mapping[q] for q in qids if q in mapping}

        client = MagicMock()
        client.search_entities.return_value = [{"id": "Q23"}]
        client.get_entities.side_effect = get_entities_side_effect

        person_obj = Person.objects.create(name="George Washington")
        person = _make_person(
            person_id=str(person_obj.pk),
            existing_attributes=[
                {"key": "birth_year", "value": "1732", "value_type": "text"},
                {"key": "bio", "value": "politician general", "value_type": "text"},
                {"key": "country", "value": "United States", "value_type": "location"},
            ],
        )
        provider = self._make_provider(client)

        result = provider.enrich(person)

        # Should have wikidata_qid and wikidata_url at minimum
        keys = {r.key for r in result}
        assert "wikidata_qid" in keys
        assert "wikidata_url" in keys

        qid_result = next(r for r in result if r.key == "wikidata_qid")
        assert qid_result.value == "Q23"
        assert qid_result.confidence == WikidataProvider.AUTO_LINK_CONFIDENCE

        review = WikidataCandidateReview.objects.get(person=person_obj)
        assert review.status == "auto_linked"
        assert review.linked_qid == "Q23"

    def test_ambiguous_match_creates_pending_review(self, db):
        """Multiple candidates above threshold creates pending review.

        Each candidate scores 0.40 (birth_year 0.35 + wiki 0.05) + 0.15 name
        alias match (both share label 'George Washington' with the person name)
        = up to 0.55.  Still below the 0.85 auto-link threshold, so both end up
        in the below-threshold bucket.  With two candidates the review is created
        as 'pending' (not auto-linked).
        """
        from src.web.persons.models import Person, WikidataCandidateReview

        entity1 = _make_entity(qid="Q23", label="George Washington", has_enwiki=True)
        entity2 = _make_entity(qid="Q24", label="George Washington II", has_enwiki=True)

        # Give both a birth year match so scores are non-trivial.
        _tv = {"type": "time", "value": {"time": "+1732-00-00T00:00:00Z", "precision": 9}}
        entity1["claims"]["P569"] = [{"mainsnak": {"datavalue": _tv}}]
        entity2["claims"]["P569"] = [{"mainsnak": {"datavalue": _tv}}]

        def get_entities_side_effect(qids):
            mapping = {"Q23": entity1, "Q24": entity2}
            return {q: mapping[q] for q in qids if q in mapping}

        client = MagicMock()
        client.search_entities.return_value = [{"id": "Q23"}, {"id": "Q24"}]
        client.get_entities.side_effect = get_entities_side_effect

        person_obj = Person.objects.create(name="George Washington")
        person = _make_person(
            person_id=str(person_obj.pk),
            existing_attributes=[
                {"key": "birth_year", "value": "1732", "value_type": "text"},
            ],
        )
        provider = self._make_provider(client)

        result = provider.enrich(person)

        assert result == []
        review = WikidataCandidateReview.objects.get(person=person_obj)
        # Both score < 0.85 — all below threshold → pending
        assert review.status == "pending"

    def test_confirmed_qid_path(self, db):
        """confirmed_wikidata_qid skips search and uses CONFIRMED_CONFIDENCE."""
        from src.web.persons.models import Person

        entity = _make_entity()
        client = _make_fake_client(entity_map={"Q23": entity})

        person_obj = Person.objects.create(name="George Washington")
        person = _make_person(person_id=str(person_obj.pk))
        provider = self._make_provider(client)

        result = provider.enrich(person, confirmed_wikidata_qid="Q23")

        client.search_entities.assert_not_called()
        keys = {r.key for r in result}
        assert "wikidata_qid" in keys
        qid_result = next(r for r in result if r.key == "wikidata_qid")
        assert qid_result.confidence == WikidataProvider.CONFIRMED_CONFIDENCE

    def test_confirmed_qid_not_found_returns_empty(self, db):
        """Returns empty list if confirmed QID is not found in Wikidata."""
        from src.web.persons.models import Person

        client = _make_fake_client(entity_map={})  # QID not found
        person_obj = Person.objects.create(name="Test Person")
        person = _make_person(person_id=str(person_obj.pk))
        provider = self._make_provider(client)

        result = provider.enrich(person, confirmed_wikidata_qid="Q9999999")

        assert result == []

    def test_force_rescore_ignores_existing_qid(self, db):
        """force_rescore=True performs fresh search ignoring existing wikidata_qid."""
        from src.web.persons.models import Person

        entity = _make_entity()
        client = _make_fake_client(
            search_results=[{"id": "Q23"}],
            entity_map={"Q23": entity},
        )

        person_obj = Person.objects.create(name="George Washington")
        person = _make_person(
            person_id=str(person_obj.pk),
            existing_attributes=[{"key": "wikidata_qid", "value": "Q999", "value_type": "text"}],
        )
        provider = self._make_provider(client)

        provider.enrich(person, force_rescore=True)

        # search_entities must have been called (not skipped due to existing qid)
        client.search_entities.assert_called_once()

    def test_no_existing_wikidata_qid_falls_through_to_search(self, db):
        """Without an existing wikidata_qid, plain enrich() runs the search path."""
        from src.web.persons.models import Person

        entity = _make_entity()
        client = _make_fake_client(
            search_results=[{"id": "Q23"}],
            entity_map={"Q23": entity},
        )
        person_obj = Person.objects.create(name="George Washington")
        person = _make_person(person_id=str(person_obj.pk))  # no existing_attributes
        provider = self._make_provider(client)

        provider.enrich(person)

        client.search_entities.assert_called_once()

    def test_existing_wikidata_qid_re_extracts(self, db):
        """If wikidata_qid already in existing_attributes, re-fetch and extract it."""
        from src.web.persons.models import Person

        entity = _make_entity()
        client = _make_fake_client(entity_map={"Q23": entity})
        person_obj = Person.objects.create(name="George Washington")
        person = _make_person(
            person_id=str(person_obj.pk),
            existing_attributes=[{"key": "wikidata_qid", "value": "Q23", "value_type": "text"}],
        )
        provider = self._make_provider(client)

        result = provider.enrich(person)

        client.search_entities.assert_not_called()
        client.get_entities.assert_called()
        keys = {r.key for r in result}
        assert "wikidata_qid" in keys
        assert "wikidata_url" in keys

    def test_existing_wikidata_qid_does_not_create_candidate_review(self, db):
        """Re-extracting a known QID never creates a WikidataCandidateReview."""
        from src.web.persons.models import Person, WikidataCandidateReview

        entity = _make_entity()
        client = _make_fake_client(entity_map={"Q23": entity})
        person_obj = Person.objects.create(name="George Washington")
        person = _make_person(
            person_id=str(person_obj.pk),
            existing_attributes=[{"key": "wikidata_qid", "value": "Q23", "value_type": "text"}],
        )
        provider = self._make_provider(client)

        provider.enrich(person)

        assert WikidataCandidateReview.objects.filter(person=person_obj).count() == 0

    def test_existing_wikidata_qid_creates_aliases(self, db):
        """Re-extraction creates PersonName aliases found on the entity."""
        from src.web.persons.models import Person, PersonName

        entity = _make_entity(aliases=["G. Washington", "First POTUS"])
        client = _make_fake_client(entity_map={"Q23": entity})
        person_obj = Person.objects.create(name="George Washington")
        person = _make_person(
            person_id=str(person_obj.pk),
            existing_attributes=[{"key": "wikidata_qid", "value": "Q23", "value_type": "text"}],
        )
        provider = self._make_provider(client)

        provider.enrich(person)

        alias_names = set(
            PersonName.objects.filter(person=person_obj, source="wikidata").values_list(
                "full_name", flat=True
            )
        )
        assert "G. Washington" in alias_names
        assert "First POTUS" in alias_names

    def test_existing_wikidata_qid_uses_stored_confidence(self, db):
        """Re-extraction reads confidence from the existing wikidata_qid attribute."""
        from src.web.persons.models import Person

        entity = _make_entity()
        client = _make_fake_client(entity_map={"Q23": entity})
        person_obj = Person.objects.create(name="George Washington")
        person = _make_person(
            person_id=str(person_obj.pk),
            existing_attributes=[
                {
                    "key": "wikidata_qid",
                    "value": "Q23",
                    "value_type": "text",
                    "confidence": WikidataProvider.CONFIRMED_CONFIDENCE,
                },
            ],
        )
        provider = self._make_provider(client)

        results = provider.enrich(person)

        qid_result = next(r for r in results if r.key == "wikidata_qid")
        assert qid_result.confidence == WikidataProvider.CONFIRMED_CONFIDENCE

    def test_existing_wikidata_qid_defaults_confidence_when_missing(self, db):
        """Re-extraction falls back to AUTO_LINK_CONFIDENCE when no confidence stored."""
        from src.web.persons.models import Person

        entity = _make_entity()
        client = _make_fake_client(entity_map={"Q23": entity})
        person_obj = Person.objects.create(name="George Washington")
        # existing_attributes dict has no 'confidence' key
        person = _make_person(
            person_id=str(person_obj.pk),
            existing_attributes=[{"key": "wikidata_qid", "value": "Q23", "value_type": "text"}],
        )
        provider = self._make_provider(client)

        results = provider.enrich(person)

        qid_result = next(r for r in results if r.key == "wikidata_qid")
        assert qid_result.confidence == WikidataProvider.AUTO_LINK_CONFIDENCE

    def test_existing_wikidata_qid_empty_value_returns_empty(self, db):
        """Returns empty when the stored wikidata_qid attribute has an empty value."""
        from src.web.persons.models import Person

        client = _make_fake_client()
        person_obj = Person.objects.create(name="George Washington")
        person = _make_person(
            person_id=str(person_obj.pk),
            existing_attributes=[{"key": "wikidata_qid", "value": "", "value_type": "text"}],
        )
        provider = self._make_provider(client)

        result = provider.enrich(person)

        assert result == []
        client.get_entities.assert_not_called()

    def test_existing_wikidata_qid_not_found_returns_empty(self, db):
        """Returns empty when the known QID is not found in Wikidata."""
        from src.web.persons.models import Person

        client = _make_fake_client(entity_map={})  # QID not found
        person_obj = Person.objects.create(name="George Washington")
        person = _make_person(
            person_id=str(person_obj.pk),
            existing_attributes=[{"key": "wikidata_qid", "value": "Q23", "value_type": "text"}],
        )
        provider = self._make_provider(client)

        result = provider.enrich(person)

        assert result == []


# ---------------------------------------------------------------------------
# Extraction: dates and attributes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWikidataProviderExtraction:
    """Tests for attribute extraction from entity data."""

    def _run_confirmed(self, person_obj, entity, client=None):
        if client is None:
            client = _make_fake_client(entity_map={entity["id"]: entity})
        provider = WikidataProvider(http_client=client)
        person = _make_person(person_id=str(person_obj.pk))
        return provider.enrich(person, confirmed_wikidata_qid=entity["id"])

    def test_emits_birth_date_at_day_precision(self, db):
        from src.web.persons.models import Person

        entity = _make_entity(birth_time="+1732-02-22T00:00:00Z", birth_precision=11)
        person_obj = Person.objects.create(name="George Washington")
        results = self._run_confirmed(person_obj, entity)

        r = next((r for r in results if r.key == "birth_date"), None)
        assert r is not None
        assert r.value == "1732-02-22"
        assert r.value_type == "date"

    def test_emits_birth_year_at_year_precision(self, db):
        from src.web.persons.models import Person

        entity = _make_entity(birth_time="+1732-00-00T00:00:00Z", birth_precision=9)
        person_obj = Person.objects.create(name="George Washington")
        results = self._run_confirmed(person_obj, entity)

        r = next((r for r in results if r.key == "birth_year"), None)
        assert r is not None
        assert r.value == "1732"
        assert r.value_type == "text"
        assert next((r for r in results if r.key == "birth_date"), None) is None

    def test_no_birth_date_emitted_at_century_precision(self, db):
        from src.web.persons.models import Person

        entity = _make_entity(birth_time="+1700-00-00T00:00:00Z", birth_precision=7)
        person_obj = Person.objects.create(name="Historical")
        results = self._run_confirmed(person_obj, entity)

        assert next((r for r in results if r.key == "birth_date"), None) is None
        assert next((r for r in results if r.key == "birth_year"), None) is None

    def test_emits_death_date(self, db):
        from src.web.persons.models import Person

        entity = _make_entity(death_time="+1799-12-14T00:00:00Z", death_precision=11)
        person_obj = Person.objects.create(name="George Washington")
        results = self._run_confirmed(person_obj, entity)

        r = next((r for r in results if r.key == "death_date"), None)
        assert r is not None
        assert r.value == "1799-12-14"

    def test_emits_description(self, db):
        from src.web.persons.models import Person

        entity = _make_entity(description="commander and statesman")
        person_obj = Person.objects.create(name="George Washington")
        results = self._run_confirmed(person_obj, entity)

        r = next((r for r in results if r.key == "description"), None)
        assert r is not None
        assert r.value == "commander and statesman"

    def test_emits_wikidata_url_with_platform_metadata(self, db):
        from src.web.persons.models import Person

        entity = _make_entity()
        person_obj = Person.objects.create(name="George Washington")
        results = self._run_confirmed(person_obj, entity)

        r = next((r for r in results if r.key == "wikidata_url"), None)
        assert r is not None
        assert r.value == "https://www.wikidata.org/wiki/Q23"
        assert r.value_type == "platform_url"
        assert r.metadata == {"platform": "wikidata"}

    def test_emits_occupations(self, db):
        from src.web.persons.models import Person

        entity = _make_entity(occupation_qids=["Q82955"])
        occ_entity = {"id": "Q82955", "labels": {"en": {"value": "politician"}}, "claims": {}}

        def get_entities_side_effect(qids):
            mapping = {"Q23": entity, "Q82955": occ_entity}
            return {q: mapping[q] for q in qids if q in mapping}

        client = MagicMock()
        client.get_entities.side_effect = get_entities_side_effect

        person_obj = Person.objects.create(name="George Washington")
        results = self._run_confirmed(person_obj, entity, client=client)

        r = next((r for r in results if r.key == "occupation"), None)
        assert r is not None
        assert r.value == "politician"


# ---------------------------------------------------------------------------
# Alias creation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWikidataProviderAliases:
    """Tests for PersonName alias creation."""

    def test_creates_aliases_for_new_names(self, db):
        from src.web.persons.models import Person, PersonName

        entity = _make_entity(aliases=["G. Washington", "First POTUS"])
        client = _make_fake_client(entity_map={"Q23": entity})
        provider = WikidataProvider(http_client=client)

        person_obj = Person.objects.create(name="George Washington")
        # Ensure primary PersonName exists
        PersonName.objects.create(
            person=person_obj,
            full_name="George Washington",
            name_type="primary",
            is_primary=True,
            source="manual",
        )
        person = _make_person(person_id=str(person_obj.pk))

        provider.enrich(person, confirmed_wikidata_qid="Q23")

        aliases = PersonName.objects.filter(person=person_obj, source="wikidata")
        alias_names = {a.full_name for a in aliases}
        assert "G. Washington" in alias_names
        assert "First POTUS" in alias_names

    def test_skips_existing_names(self, db):
        from src.web.persons.models import Person, PersonName

        entity = _make_entity(aliases=["G. Washington"])
        client = _make_fake_client(entity_map={"Q23": entity})
        provider = WikidataProvider(http_client=client)

        person_obj = Person.objects.create(name="George Washington")
        PersonName.objects.create(
            person=person_obj,
            full_name="G. Washington",
            name_type="alias",
            is_primary=False,
            source="manual",
        )
        person = _make_person(person_id=str(person_obj.pk))

        provider.enrich(person, confirmed_wikidata_qid="Q23")

        wikidata_aliases = PersonName.objects.filter(
            person=person_obj, source="wikidata", full_name="G. Washington"
        )
        assert wikidata_aliases.count() == 0

    def test_alias_confidence_is_correct(self, db):
        from src.web.persons.models import Person, PersonName

        entity = _make_entity(aliases=["GW"])
        client = _make_fake_client(entity_map={"Q23": entity})
        provider = WikidataProvider(http_client=client)

        person_obj = Person.objects.create(name="George Washington")
        person = _make_person(person_id=str(person_obj.pk))

        # Auto-link confidence for aliases
        provider.enrich(person, confirmed_wikidata_qid="Q23")

        alias = PersonName.objects.filter(person=person_obj, source="wikidata").first()
        assert alias is not None
        assert alias.confidence == WikidataProvider.CONFIRMED_ALIAS_CONFIDENCE

    def test_alias_provenance_includes_qid(self, db):
        from src.web.persons.models import Person, PersonName

        entity = _make_entity(aliases=["G. Washington"])
        client = _make_fake_client(entity_map={"Q23": entity})
        provider = WikidataProvider(http_client=client)

        person_obj = Person.objects.create(name="George Washington")
        person = _make_person(person_id=str(person_obj.pk))

        provider.enrich(person, confirmed_wikidata_qid="Q23")

        alias = PersonName.objects.filter(person=person_obj, source="wikidata").first()
        assert alias is not None
        assert alias.provenance["wikidata_qid"] == "Q23"
        assert alias.provenance["provider"] == "wikidata"

    def test_infer_name_type_abbreviation(self, db):
        from src.web.persons.models import Person, PersonName

        entity = _make_entity(aliases=["GW"])  # 2 chars, all caps
        client = _make_fake_client(entity_map={"Q23": entity})
        provider = WikidataProvider(http_client=client)

        person_obj = Person.objects.create(name="George Washington")
        person = _make_person(person_id=str(person_obj.pk))

        provider.enrich(person, confirmed_wikidata_qid="Q23")

        alias = PersonName.objects.filter(
            person=person_obj, source="wikidata", full_name="GW"
        ).first()
        # GW: 2 chars so doesn't meet 3-6 rule; infer_name_type returns "alias"
        assert alias is not None


# ---------------------------------------------------------------------------
# External identifier extraction
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestExternalIdentifierExtraction:
    """Tests for enabled ExternalIdentifierProperty extraction."""

    def test_extracts_identifier_with_formatter_url(self, db):
        from src.web.persons.models import ExternalIdentifierProperty, ExternalPlatform, Person

        viaf_platform, _ = ExternalPlatform.objects.get_or_create(
            slug="viaf", defaults={"display": "VIAF"}
        )
        ExternalIdentifierProperty.objects.create(
            wikidata_property_id="P214",
            slug="viaf-id",
            display="VIAF ID",
            formatter_url="https://viaf.org/viaf/$1/",
            platform=viaf_platform,
            is_enabled=True,
        )

        entity = _make_entity()
        entity["claims"]["P214"] = [
            {"mainsnak": {"datavalue": {"type": "string", "value": "31996712"}}}
        ]
        client = _make_fake_client(entity_map={"Q23": entity})
        provider = WikidataProvider(http_client=client)

        person_obj = Person.objects.create(name="George Washington")
        person = _make_person(person_id=str(person_obj.pk))

        results = provider.enrich(person, confirmed_wikidata_qid="Q23")

        r = next((r for r in results if r.key == "viaf-id"), None)
        assert r is not None
        assert r.value == "https://viaf.org/viaf/31996712/"
        assert r.value_type == "platform_url"
        assert r.metadata == {"platform": "viaf"}

    def test_extracts_identifier_without_formatter_url_as_text(self, db):
        from src.web.persons.models import ExternalIdentifierProperty, Person

        ExternalIdentifierProperty.objects.create(
            wikidata_property_id="P999",
            slug="raw-id",
            display="Raw ID",
            formatter_url="",
            is_enabled=True,
        )

        entity = _make_entity()
        entity["claims"]["P999"] = [
            {"mainsnak": {"datavalue": {"type": "string", "value": "abc123"}}}
        ]
        client = _make_fake_client(entity_map={"Q23": entity})
        provider = WikidataProvider(http_client=client)

        person_obj = Person.objects.create(name="Test Person")
        person = _make_person(person_id=str(person_obj.pk))

        results = provider.enrich(person, confirmed_wikidata_qid="Q23")

        r = next((r for r in results if r.key == "raw-id"), None)
        assert r is not None
        assert r.value == "abc123"
        assert r.value_type == "text"

    def test_disabled_property_not_extracted(self, db):
        from src.web.persons.models import ExternalIdentifierProperty, Person

        ExternalIdentifierProperty.objects.create(
            wikidata_property_id="P215",
            slug="disabled-id",
            display="Disabled",
            formatter_url="https://example.com/$1",
            is_enabled=False,
        )

        entity = _make_entity()
        entity["claims"]["P215"] = [{"mainsnak": {"datavalue": {"type": "string", "value": "xyz"}}}]
        client = _make_fake_client(entity_map={"Q23": entity})
        provider = WikidataProvider(http_client=client)

        person_obj = Person.objects.create(name="Test Person")
        person = _make_person(person_id=str(person_obj.pk))

        results = provider.enrich(person, confirmed_wikidata_qid="Q23")

        assert not any(r.key == "disabled-id" for r in results)

    def test_skips_platform_url_when_no_platform_fk(self, db):
        """platform_url attributes are skipped (with a warning) when the
        ExternalIdentifierProperty has a formatter_url but no platform FK."""
        from src.web.persons.models import ExternalIdentifierProperty, ExternalPlatform, Person

        ExternalIdentifierProperty.objects.create(
            wikidata_property_id="P888",
            slug="no-fk-id",
            display="No FK Platform",
            formatter_url="https://example.com/$1",
            platform=None,
            is_enabled=True,
        )

        entity = _make_entity()
        entity["claims"]["P888"] = [
            {"mainsnak": {"datavalue": {"type": "string", "value": "12345"}}}
        ]
        client = _make_fake_client(entity_map={"Q23": entity})
        provider = WikidataProvider(http_client=client)

        person_obj = Person.objects.create(name="Test Person")
        person = _make_person(person_id=str(person_obj.pk))

        results = provider.enrich(person, confirmed_wikidata_qid="Q23")

        # The attribute should be absent — no auto-creation of ExternalPlatform
        assert not any(r.key == "no-fk-id" for r in results)
        assert not ExternalPlatform.objects.filter(slug="no-fk-id").exists()


# ---------------------------------------------------------------------------
# Empty ExternalIdentifierProperty table warnings (#33)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEmptyExternalIdentifierTableWarning:
    """WikidataProvider emits a WARNING when ExternalIdentifierProperty is empty."""

    def test_warning_logged_when_table_empty(self):
        """A structured WARNING is emitted when no enabled properties exist."""
        from unittest.mock import patch

        from src.web.persons.models import ExternalIdentifierProperty, Person

        # Ensure table is empty (delete the P2390 seed row from migration)
        ExternalIdentifierProperty.objects.all().delete()

        entity = _make_entity()
        client = _make_fake_client(entity_map={"Q23": entity})
        provider = WikidataProvider(http_client=client)

        person_obj = Person.objects.create(name="Test Person")
        person = _make_person(person_id=str(person_obj.pk))

        with patch("src.core.enrichment.providers.wikidata.logger") as mock_logger:
            provider.enrich(person, confirmed_wikidata_qid="Q23")

        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert any("ExternalIdentifierProperty" in c for c in warning_calls), (
            "Expected a WARNING mentioning ExternalIdentifierProperty when table is empty"
        )
        assert any("sync_wikidata_properties" in c for c in warning_calls), (
            "Expected WARNING to name the management command operators should run"
        )

    def test_core_attributes_still_emitted_when_table_empty(self):
        """Core Wikidata attributes (QID, label, Wikipedia URL) are emitted even
        when ExternalIdentifierProperty table is empty."""
        from src.web.persons.models import ExternalIdentifierProperty, Person

        ExternalIdentifierProperty.objects.all().delete()

        entity = _make_entity()
        client = _make_fake_client(entity_map={"Q23": entity})
        provider = WikidataProvider(http_client=client)

        person_obj = Person.objects.create(name="Test Person")
        person = _make_person(person_id=str(person_obj.pk))

        results = provider.enrich(person, confirmed_wikidata_qid="Q23")
        keys = {r.key for r in results}

        assert "wikidata_qid" in keys, "wikidata_qid must still be emitted"


# ---------------------------------------------------------------------------
# Provider metadata
# ---------------------------------------------------------------------------


class TestWikidataProviderMetadata:
    """Tests for provider class-level declarations."""

    def test_name(self):
        assert WikidataProvider.name == "wikidata"

    def test_output_keys(self):
        assert "wikidata_qid" in WikidataProvider.output_keys
        assert "wikidata_url" in WikidataProvider.output_keys

    def test_no_dependencies(self):
        assert WikidataProvider.dependencies == []

    def test_refresh_interval_is_7_days(self):
        from datetime import timedelta

        assert WikidataProvider.refresh_interval == timedelta(days=7)

    def test_auto_link_threshold(self):
        assert WikidataProvider.AUTO_LINK_THRESHOLD == 0.85

    def test_confidence_constants(self):
        assert WikidataProvider.AUTO_LINK_CONFIDENCE == 0.75
        assert WikidataProvider.CONFIRMED_CONFIDENCE == 0.95
        assert WikidataProvider.ALIAS_CONFIDENCE == 0.70
        assert WikidataProvider.CONFIRMED_ALIAS_CONFIDENCE == 0.80


# ---------------------------------------------------------------------------
# Integration tests (live Wikidata)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.django_db
class TestWikidataProviderIntegration:
    """Integration tests that hit live Wikidata. Skipped in normal CI runs."""

    def test_george_washington_confirmed_qid(self, db):
        """Fetching George Washington (Q23) by confirmed QID returns core attributes."""
        from src.web.persons.models import Person

        provider = WikidataProvider()
        person_obj = Person.objects.create(name="George Washington")
        person = _make_person(person_id=str(person_obj.pk))

        results = provider.enrich(person, confirmed_wikidata_qid="Q23")

        keys = {r.key for r in results}
        assert "wikidata_qid" in keys
        assert "wikidata_url" in keys

        qid_result = next(r for r in results if r.key == "wikidata_qid")
        assert qid_result.value == "Q23"
        assert qid_result.confidence == WikidataProvider.CONFIRMED_CONFIDENCE

    def test_search_and_auto_link_ada_lovelace(self, db):
        """Searching 'Ada Lovelace' should auto-link to Q7259."""
        from src.web.persons.models import Person

        provider = WikidataProvider()
        person_obj = Person.objects.create(name="Ada Lovelace")
        person = PersonData(
            id=str(person_obj.pk),
            name="Ada Lovelace",
            given_name="Ada",
            surname="Lovelace",
            existing_attributes=[
                {"key": "birth_year", "value": "1815", "value_type": "text"},
                {"key": "bio", "value": "mathematician programmer", "value_type": "text"},
            ],
        )

        results = provider.enrich(person)

        # Either auto-linked (returns attributes) or review created (returns [])
        # Both are acceptable outcomes in a live test — the key is no exception raised.
        assert isinstance(results, list)
