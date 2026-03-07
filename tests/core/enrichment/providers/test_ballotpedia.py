"""Tests for BallotpediaProvider.

Unit tests use a mocked requests.Session so no real HTTP calls are made.
Integration tests (marked @pytest.mark.integration) hit live Ballotpedia.
"""

from unittest.mock import MagicMock

import pytest
import requests

from src.core.enrichment.base import NoMatchSignal, PersonData
from src.core.enrichment.providers.ballotpedia import BallotpediaProvider

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_SLUG = "Nancy_Pelosi"
_BP_URL = "https://ballotpedia.org/Nancy_Pelosi"

# Minimal wikitext with an officeholder infobox
_WIKITEXT_FULL = """\
{{Infobox officeholder
|name=Nancy Pelosi
|birth_date={{birth date|1940|3|26}}
|party=Democratic Party
|state=California
|office=Speaker of the House
}}
Some article text here.
"""

# Wikitext with no officeholder infobox
_WIKITEXT_NO_INFOBOX = """\
This is just some text with no infobox.
"""

# Wikitext with a different infobox (not officeholder)
_WIKITEXT_WRONG_INFOBOX = """\
{{Infobox person
|name=Some Person
}}
"""


def _person(slug: str = _SLUG, extra_attrs: list[dict] | None = None) -> PersonData:
    """Return a PersonData with wikidata_qid and ballotpedia-slug attributes."""
    attrs = [
        {"key": "wikidata_qid", "value": "Q106139", "value_type": "text", "source": "wikidata"},
        {"key": "ballotpedia-slug", "value": slug, "value_type": "text", "source": "wikidata"},
    ]
    if extra_attrs:
        attrs.extend(extra_attrs)
    return PersonData(
        id="01JPERSON0000000000000000",
        name="Nancy Pelosi",
        given_name="Nancy",
        surname="Pelosi",
        existing_attributes=attrs,
    )


def _person_no_slug() -> PersonData:
    """Return a PersonData with no ballotpedia-slug attribute."""
    return PersonData(
        id="01JPERSON0000000000000000",
        name="Some Person",
        existing_attributes=[
            {"key": "wikidata_qid", "value": "Q999", "value_type": "text", "source": "wikidata"},
        ],
    )


def _make_api_response(wikitext: str, missing: bool = False) -> dict:
    """Build a minimal Ballotpedia MediaWiki API response."""
    if missing:
        return {"query": {"pages": {"-1": {"missing": "", "title": "Missing_Page"}}}}
    return {
        "query": {
            "pages": {
                "12345": {
                    "pageid": 12345,
                    "title": "Nancy Pelosi",
                    "revisions": [{"*": wikitext}],
                }
            }
        }
    }


def _make_provider(
    response: dict | None = None, http_error: Exception | None = None
) -> BallotpediaProvider:
    """Return a BallotpediaProvider with mocked HTTP session."""
    provider = BallotpediaProvider()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = response or {}

    if http_error:
        provider._session.get = MagicMock(side_effect=http_error)
    else:
        provider._session.get = MagicMock(return_value=mock_resp)
    return provider


# ---------------------------------------------------------------------------
# Provider metadata
# ---------------------------------------------------------------------------


def test_provider_name():
    assert BallotpediaProvider.name == "ballotpedia"


def test_output_keys():
    assert set(BallotpediaProvider.output_keys) == {
        "ballotpedia_url",
        "party",
        "office_held",
        "state",
        "birth_date",
    }


def test_dependencies_declared():
    deps = {d.attribute_key: d for d in BallotpediaProvider.dependencies}
    assert "wikidata_qid" in deps
    assert deps["wikidata_qid"].skip_if_absent is True
    assert "ballotpedia-slug" in deps
    assert deps["ballotpedia-slug"].skip_if_absent is True


def test_required_platforms():
    assert "ballotpedia" in BallotpediaProvider.required_platforms


def test_refresh_interval_is_one_day():
    from datetime import timedelta

    assert BallotpediaProvider.refresh_interval == timedelta(days=1)


# ---------------------------------------------------------------------------
# can_run gate
# ---------------------------------------------------------------------------


def test_can_run_true_when_both_deps_present():
    provider = BallotpediaProvider()
    assert (
        provider.can_run({"wikidata_qid", "ballotpedia-slug"}, active_platforms={"ballotpedia"})
        is True
    )


def test_can_run_false_when_slug_absent():
    provider = BallotpediaProvider()
    assert provider.can_run({"wikidata_qid"}, active_platforms={"ballotpedia"}) is False


def test_can_run_false_when_platform_inactive():
    provider = BallotpediaProvider()
    assert provider.can_run({"wikidata_qid", "ballotpedia-slug"}, active_platforms=set()) is False


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_enrich_returns_ballotpedia_url():
    provider = _make_provider(response=_make_api_response(_WIKITEXT_FULL))
    results = provider.enrich(_person())
    keys = {r.key for r in results}
    assert "ballotpedia_url" in keys

    url_result = next(r for r in results if r.key == "ballotpedia_url")
    assert url_result.value == _BP_URL
    assert url_result.value_type == "platform_url"
    assert url_result.metadata == {"platform": "ballotpedia"}


def test_enrich_extracts_party():
    provider = _make_provider(response=_make_api_response(_WIKITEXT_FULL))
    results = provider.enrich(_person())
    party_result = next((r for r in results if r.key == "party"), None)
    assert party_result is not None
    assert party_result.value == "Democratic Party"
    assert party_result.value_type == "text"


def test_enrich_extracts_state():
    provider = _make_provider(response=_make_api_response(_WIKITEXT_FULL))
    results = provider.enrich(_person())
    state_result = next((r for r in results if r.key == "state"), None)
    assert state_result is not None
    assert state_result.value == "California"
    assert state_result.value_type == "text"


def test_enrich_extracts_office_held():
    provider = _make_provider(response=_make_api_response(_WIKITEXT_FULL))
    results = provider.enrich(_person())
    office_result = next((r for r in results if r.key == "office_held"), None)
    assert office_result is not None
    assert "Speaker" in office_result.value
    assert office_result.value_type == "text"


def test_enrich_extracts_birth_date():
    provider = _make_provider(response=_make_api_response(_WIKITEXT_FULL))
    results = provider.enrich(_person())
    birth_result = next((r for r in results if r.key == "birth_date"), None)
    assert birth_result is not None
    assert birth_result.value == "1940-03-26"
    assert birth_result.value_type == "date"


def test_enrich_calls_api_with_correct_params():
    provider = _make_provider(response=_make_api_response(_WIKITEXT_FULL))
    provider.enrich(_person())
    call_kwargs = provider._session.get.call_args
    assert call_kwargs is not None
    # Verify the call was to the Ballotpedia API endpoint
    called_url = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1].get("url", "")
    assert "ballotpedia.org" in called_url


# ---------------------------------------------------------------------------
# Skip-if-already-present logic
# ---------------------------------------------------------------------------


def test_skips_birth_date_if_already_present():
    """birth_date should not be re-emitted if already in existing_attributes."""
    person = _person(
        extra_attrs=[
            {
                "key": "birth_date",
                "value": "1940-03-26",
                "value_type": "date",
                "source": "wikidata",
            }
        ]
    )
    provider = _make_provider(response=_make_api_response(_WIKITEXT_FULL))
    results = provider.enrich(person)
    birth_keys = [r for r in results if r.key == "birth_date"]
    assert len(birth_keys) == 0


def test_skips_party_if_already_present():
    """party should not be re-emitted if already in existing_attributes."""
    person = _person(
        extra_attrs=[
            {
                "key": "party",
                "value": "Democratic Party",
                "value_type": "text",
                "source": "wikidata",
            }
        ]
    )
    provider = _make_provider(response=_make_api_response(_WIKITEXT_FULL))
    results = provider.enrich(person)
    party_keys = [r for r in results if r.key == "party"]
    assert len(party_keys) == 0


def test_skips_state_if_already_present():
    person = _person(
        extra_attrs=[
            {"key": "state", "value": "California", "value_type": "text", "source": "wikidata"}
        ]
    )
    provider = _make_provider(response=_make_api_response(_WIKITEXT_FULL))
    results = provider.enrich(person)
    state_keys = [r for r in results if r.key == "state"]
    assert len(state_keys) == 0


# ---------------------------------------------------------------------------
# No-match paths
# ---------------------------------------------------------------------------


def test_no_match_when_slug_attribute_missing():
    provider = _make_provider(response=_make_api_response(_WIKITEXT_FULL))
    with pytest.raises(NoMatchSignal):
        provider.enrich(_person_no_slug())


def test_no_match_when_page_missing():
    """MediaWiki API returns missing page marker → NoMatchSignal."""
    provider = _make_provider(response=_make_api_response("", missing=True))
    with pytest.raises(NoMatchSignal):
        provider.enrich(_person())


def test_no_match_when_no_officeholder_infobox():
    """Wikitext with no officeholder infobox → NoMatchSignal."""
    provider = _make_provider(response=_make_api_response(_WIKITEXT_NO_INFOBOX))
    with pytest.raises(NoMatchSignal):
        provider.enrich(_person())


def test_no_match_when_wrong_infobox_type():
    """Wikitext with non-officeholder infobox → NoMatchSignal."""
    provider = _make_provider(response=_make_api_response(_WIKITEXT_WRONG_INFOBOX))
    with pytest.raises(NoMatchSignal):
        provider.enrich(_person())


def test_http_error_propagates():
    """Non-recoverable HTTP errors re-raise."""
    resp = MagicMock()
    resp.status_code = 503
    error = requests.HTTPError(response=resp)
    provider = BallotpediaProvider()
    provider._session = MagicMock()
    provider._session.get.side_effect = error
    with pytest.raises(requests.HTTPError):
        provider.enrich(_person())


# ---------------------------------------------------------------------------
# Infobox field edge cases
# ---------------------------------------------------------------------------


def test_missing_optional_fields_do_not_raise():
    """Wikitext with officeholder infobox but missing party/state/office.

    Expect no error and at least ballotpedia_url in partial results.
    """
    wikitext = "{{Infobox officeholder\n|name=Sparse Person\n}}"
    provider = _make_provider(response=_make_api_response(wikitext))
    # Should not raise — just returns ballotpedia_url with whatever is parseable
    results = provider.enrich(_person())
    assert any(r.key == "ballotpedia_url" for r in results)


def test_birth_date_alternate_format():
    """birth_date with {{birth date and age}} template is also parsed."""
    wikitext = """\
{{Infobox officeholder
|name=Joe Biden
|birth_date={{birth date and age|1942|11|20}}
|party=Democratic Party
|state=Delaware
}}
"""
    provider = _make_provider(response=_make_api_response(wikitext))
    results = provider.enrich(_person())
    birth_result = next((r for r in results if r.key == "birth_date"), None)
    assert birth_result is not None
    assert birth_result.value == "1942-11-20"


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_integration_nancy_pelosi():
    """Live test: enrich Nancy Pelosi from real Ballotpedia."""
    provider = BallotpediaProvider()
    person = PersonData(
        id="01JPERSON0000000000000000",
        name="Nancy Pelosi",
        given_name="Nancy",
        surname="Pelosi",
        existing_attributes=[
            {"key": "wikidata_qid", "value": "Q106139", "value_type": "text", "source": "wikidata"},
            {
                "key": "ballotpedia-slug",
                "value": "Nancy_Pelosi",
                "value_type": "text",
                "source": "wikidata",
            },
        ],
    )
    results = provider.enrich(person)
    keys = {r.key for r in results}
    assert "ballotpedia_url" in keys
    url_result = next(r for r in results if r.key == "ballotpedia_url")
    assert url_result.value == "https://ballotpedia.org/Nancy_Pelosi"
    assert "party" in keys
