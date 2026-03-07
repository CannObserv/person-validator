"""Tests for WikipediaProvider.

Unit tests use a fake WikimediaHttpClient so no real HTTP calls are made.
Integration tests (marked @pytest.mark.integration) hit live Wikipedia/Wikidata.
"""

from unittest.mock import MagicMock

import pytest
import requests

from src.core.enrichment.base import NoMatchSignal, PersonData
from src.core.enrichment.providers.wikipedia import WikipediaProvider

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_QID = "Q23"
_TITLE = "George_Washington"
_ARTICLE_URL = "https://en.wikipedia.org/wiki/George_Washington"
_EXTRACT = (
    "George Washington (February 22, 1732 – December 14, 1799) was an American Founding Father."
)


def _person(qid: str = _QID) -> PersonData:
    """Return a PersonData with a wikidata_qid attribute."""
    return PersonData(
        id="01JPERSON0000000000000000",
        name="George Washington",
        given_name="George",
        surname="Washington",
        existing_attributes=[
            {
                "key": "wikidata_qid",
                "value": qid,
                "value_type": "text",
                "source": "wikidata",
            }
        ],
    )


def _person_no_qid() -> PersonData:
    """Return a PersonData with no wikidata_qid attribute."""
    return PersonData(
        id="01JPERSON0000000000000000",
        name="Unknown Person",
        existing_attributes=[],
    )


def _make_entity(qid: str = _QID, has_enwiki: bool = True, title: str = _TITLE) -> dict:
    """Build a minimal Wikidata entity dict."""
    sitelinks = {"enwiki": {"title": title}} if has_enwiki else {}
    return {
        "id": qid,
        "labels": {"en": {"value": "George Washington"}},
        "claims": {},
        "sitelinks": sitelinks,
    }


def _make_summary_response(title: str = _TITLE, extract: str = _EXTRACT) -> dict:
    """Build a minimal Wikipedia REST API summary response."""
    return {
        "title": title,
        "displaytitle": title.replace("_", " "),
        "description": "1st president of the United States",
        "extract": extract,
        "content_urls": {"desktop": {"page": f"https://en.wikipedia.org/wiki/{title}"}},
    }


def _make_provider(entity: dict | None = None, summary: dict | None = None) -> WikipediaProvider:
    """Return a WikipediaProvider with mocked HTTP client."""
    client = MagicMock()
    if entity is not None:
        client.get_entities.return_value = {entity["id"]: entity}
    else:
        client.get_entities.return_value = {}
    client.get_wikipedia_summary.return_value = summary
    return WikipediaProvider(client=client)


# ---------------------------------------------------------------------------
# Provider metadata
# ---------------------------------------------------------------------------


def test_provider_name():
    provider = WikipediaProvider()
    assert provider.name == "wikipedia"


def test_output_keys():
    assert set(WikipediaProvider.output_keys) == {"wikipedia_url", "wikipedia_extract"}


def test_dependency_declared():
    deps = WikipediaProvider.dependencies
    assert len(deps) == 1
    dep = deps[0]
    assert dep.attribute_key == "wikidata_qid"
    assert dep.skip_if_absent is True


def test_required_platforms():
    assert "wikipedia" in WikipediaProvider.required_platforms


# ---------------------------------------------------------------------------
# can_run gate
# ---------------------------------------------------------------------------


def test_can_run_true_when_qid_present_and_platform_active():
    provider = WikipediaProvider()
    assert provider.can_run({"wikidata_qid"}, active_platforms={"wikipedia"}) is True


def test_can_run_false_when_qid_absent():
    provider = WikipediaProvider()
    assert provider.can_run(set(), active_platforms={"wikipedia"}) is False


def test_can_run_false_when_platform_inactive():
    provider = WikipediaProvider()
    assert provider.can_run({"wikidata_qid"}, active_platforms=set()) is False


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_enrich_returns_url_and_extract():
    provider = _make_provider(
        entity=_make_entity(has_enwiki=True),
        summary=_make_summary_response(),
    )
    results = provider.enrich(_person())

    keys = {r.key for r in results}
    assert keys == {"wikipedia_url", "wikipedia_extract"}

    url_result = next(r for r in results if r.key == "wikipedia_url")
    extract_result = next(r for r in results if r.key == "wikipedia_extract")

    assert url_result.value == _ARTICLE_URL
    assert url_result.value_type == "platform_url"
    assert url_result.metadata == {"platform": "wikipedia"}
    assert url_result.confidence == pytest.approx(0.90)

    assert extract_result.value == _EXTRACT
    assert extract_result.value_type == "text"
    assert extract_result.confidence == pytest.approx(0.90)


def test_enrich_calls_get_entities_with_qid():
    entity = _make_entity()
    provider = _make_provider(entity=entity, summary=_make_summary_response())
    provider.enrich(_person())
    provider._client.get_entities.assert_called_once_with([_QID])


def test_enrich_calls_get_wikipedia_summary_with_title():
    entity = _make_entity()
    provider = _make_provider(entity=entity, summary=_make_summary_response())
    provider.enrich(_person())
    provider._client.get_wikipedia_summary.assert_called_once_with(_TITLE)


# ---------------------------------------------------------------------------
# No-match paths
# ---------------------------------------------------------------------------


def test_no_match_when_entity_not_found():
    """Entity missing from wbgetentities response → NoMatchSignal."""
    client = MagicMock()
    client.get_entities.return_value = {}  # empty — QID not found
    provider = WikipediaProvider(client=client)
    with pytest.raises(NoMatchSignal):
        provider.enrich(_person())


def test_no_match_when_no_enwiki_sitelink():
    """Entity found but has no enwiki sitelink → NoMatchSignal."""
    provider = _make_provider(
        entity=_make_entity(has_enwiki=False),
        summary=None,
    )
    with pytest.raises(NoMatchSignal):
        provider.enrich(_person())


def test_no_match_when_wikipedia_returns_404():
    """Wikipedia REST API 404 → NoMatchSignal."""
    client = MagicMock()
    client.get_entities.return_value = {_QID: _make_entity(has_enwiki=True)}
    resp = MagicMock()
    resp.status_code = 404
    client.get_wikipedia_summary.side_effect = requests.HTTPError(response=resp)
    provider = WikipediaProvider(client=client)
    with pytest.raises(NoMatchSignal):
        provider.enrich(_person())


def test_non_404_http_error_propagates():
    """Non-404 HTTP errors (e.g. 503) are re-raised, not caught."""
    client = MagicMock()
    client.get_entities.return_value = {_QID: _make_entity(has_enwiki=True)}
    resp = MagicMock()
    resp.status_code = 503
    client.get_wikipedia_summary.side_effect = requests.HTTPError(response=resp)
    provider = WikipediaProvider(client=client)
    with pytest.raises(requests.HTTPError):
        provider.enrich(_person())


def test_no_match_when_qid_attribute_missing():
    """If wikidata_qid is not in existing_attributes, raise NoMatchSignal."""
    provider = _make_provider(entity=_make_entity())
    with pytest.raises(NoMatchSignal):
        provider.enrich(_person_no_qid())


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_title_with_spaces_in_sitelink():
    """Sitelink title is used verbatim (may include underscores or spaces)."""
    title = "Barack_Obama"
    entity = _make_entity(qid="Q76", title=title)
    summary = _make_summary_response(
        title=title,
        extract="Barack Obama is the 44th president.",
    )
    client = MagicMock()
    client.get_entities.return_value = {"Q76": entity}
    client.get_wikipedia_summary.return_value = summary
    provider = WikipediaProvider(client=client)

    person = PersonData(
        id="01JPERSON0000000000000001",
        name="Barack Obama",
        existing_attributes=[
            {"key": "wikidata_qid", "value": "Q76", "value_type": "text", "source": "wikidata"}
        ],
    )
    results = provider.enrich(person)
    url_result = next(r for r in results if r.key == "wikipedia_url")
    assert url_result.value == "https://en.wikipedia.org/wiki/Barack_Obama"


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_integration_george_washington():
    """Live test: enrich George Washington (Q23) from real Wikipedia/Wikidata."""
    provider = WikipediaProvider()
    person = PersonData(
        id="01JPERSON0000000000000000",
        name="George Washington",
        given_name="George",
        surname="Washington",
        existing_attributes=[
            {
                "key": "wikidata_qid",
                "value": "Q23",
                "value_type": "text",
                "source": "wikidata",
            }
        ],
    )
    results = provider.enrich(person)
    keys = {r.key for r in results}
    assert "wikipedia_url" in keys
    assert "wikipedia_extract" in keys

    url_result = next(r for r in results if r.key == "wikipedia_url")
    assert "George_Washington" in url_result.value or "George Washington" in url_result.value
    assert url_result.value.startswith("https://en.wikipedia.org/wiki/")

    extract_result = next(r for r in results if r.key == "wikipedia_extract")
    assert len(extract_result.value) > 50
