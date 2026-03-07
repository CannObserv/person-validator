"""Tests for src.core.enrichment.tasks."""

from unittest.mock import patch

import pytest

from src.core.enrichment.tasks import run_enrichment_for_person


@pytest.mark.django_db
class TestRunEnrichmentForPersonConfirmedQid:
    """confirmed_wikidata_qid is forwarded to WikidataProvider.enrich() via runner.

    Regression: previously tasks.py injected a synthetic wikidata_qid attribute
    into existing_attributes but never passed confirmed_wikidata_qid to the
    runner.  WikidataProvider then detected the synthetic attribute and returned
    early with "person already has wikidata_qid; skipping search", producing 0
    attributes and 0 names despite a valid confirmed QID.
    """

    def test_confirmed_qid_forwarded_to_provider(self):
        """run_enrichment_for_person passes confirmed_wikidata_qid to the provider."""
        from src.web.persons.models import Person

        person = Person.objects.create(name="Denny Heck")

        captured: dict = {}

        def capturing_enrich(self_provider, person_data, **kwargs):  # noqa: ANN001
            captured.update(kwargs)
            return []

        with patch(
            "src.core.enrichment.providers.wikidata.WikidataProvider.enrich",
            capturing_enrich,
        ):
            run_enrichment_for_person(
                person_id=str(person.pk),
                triggered_by="test",
                confirmed_wikidata_qid="Q4068793",
            )

        assert captured.get("confirmed_wikidata_qid") == "Q4068793", (
            "confirmed_wikidata_qid was not forwarded to WikidataProvider.enrich(); "
            "the provider would skip extraction if only a synthetic attribute is injected."
        )

    def test_no_confirmed_qid_does_not_inject_kwarg(self):
        """Without confirmed_wikidata_qid, the provider receives no extra kwargs."""
        from src.web.persons.models import Person

        person = Person.objects.create(name="Test Person")

        captured: dict = {"_sentinel": True}

        def capturing_enrich(self_provider, person_data, **kwargs):  # noqa: ANN001
            captured.clear()
            captured.update(kwargs)
            return []

        with patch(
            "src.core.enrichment.providers.wikidata.WikidataProvider.enrich",
            capturing_enrich,
        ):
            run_enrichment_for_person(
                person_id=str(person.pk),
                triggered_by="test",
            )

        assert captured == {}, "Expected no extra kwargs when confirmed_wikidata_qid is None"
