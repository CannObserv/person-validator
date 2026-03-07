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
        from src.web.persons.models import Person  # noqa: PLC0415

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
        from src.web.persons.models import Person  # noqa: PLC0415

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

    def test_force_rescore_forwarded_to_provider(self):
        """force_rescore=True is forwarded to WikidataProvider.enrich() as a kwarg.

        tasks.py strips wikidata_qid from existing_attributes when force_rescore
        is True, but that only handles the in-memory PersonData snapshot.  If a
        persisted wikidata_qid attribute is present in the DB at runner time
        (e.g. a concurrent write), the kwarg is the authoritative signal that
        the provider should ignore it and perform a fresh search.
        """
        from src.web.persons.models import Person  # noqa: PLC0415

        person = Person.objects.create(name="Test Person")

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
                force_rescore=True,
            )

        assert captured.get("force_rescore") is True, (
            "force_rescore was not forwarded to WikidataProvider.enrich()"
        )
