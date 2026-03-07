"""Tests for BallotpediaProvider.

Unit tests use a mocked requests.Session so no real HTTP calls are made.
Integration tests (marked @pytest.mark.integration) hit live Ballotpedia.

Design notes:
  - BallotpediaProvider fetches page *categories* from the Ballotpedia MediaWiki API
    (``prop=categories``) rather than wikitext.  The infobox-based approach was
    abandoned because Ballotpedia has migrated all modern pages to BPW widgets.
  - ``ballotpedia_url`` is always emitted when the page exists.
  - ``party`` is inferred from category membership (e.g. ``Democratic Party``).
  - ``NoMatchSignal`` fires only when the slug attribute is absent or the page
    itself is missing — not when categories yield no additional attributes.
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


def _make_api_response(
    categories: list[str] | None = None,
    missing: bool = False,
) -> dict:
    """Build a minimal Ballotpedia MediaWiki API categories response."""
    if missing:
        return {"query": {"pages": {"-1": {"missing": "", "title": "Missing_Page"}}}}
    cat_list = [{"ns": 14, "title": f"Category:{c}"} for c in (categories or [])]
    return {
        "batchcomplete": "",
        "query": {
            "pages": {
                "12345": {
                    "pageid": 12345,
                    "title": "Nancy Pelosi",
                    "categories": cat_list,
                }
            }
        },
    }


def _make_provider(
    response: dict | None = None, http_error: Exception | None = None
) -> BallotpediaProvider:
    """Return a BallotpediaProvider with mocked HTTP session."""
    provider = BallotpediaProvider()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = response or {}

    if http_error is not None:
        provider._session = MagicMock()
        provider._session.get.side_effect = http_error
    else:
        provider._session = MagicMock()
        provider._session.get.return_value = mock_resp

    return provider


# ---------------------------------------------------------------------------
# Provider metadata
# ---------------------------------------------------------------------------


def test_provider_name():
    assert BallotpediaProvider.name == "ballotpedia"


def test_output_keys():
    """Output keys should be exactly ballotpedia_url and party."""
    assert set(BallotpediaProvider.output_keys) == {"ballotpedia_url", "party"}


def test_dependencies_declared():
    deps = {d.attribute_key: d for d in BallotpediaProvider.dependencies}
    assert deps["wikidata_qid"].skip_if_absent is True
    assert deps["ballotpedia-slug"].skip_if_absent is True


def test_required_platforms():
    assert "ballotpedia" in BallotpediaProvider.required_platforms


def test_refresh_interval_is_one_day():
    from datetime import timedelta

    assert BallotpediaProvider.refresh_interval == timedelta(days=1)


# ---------------------------------------------------------------------------
# can_run() checks
# ---------------------------------------------------------------------------


def test_can_run_true_when_both_deps_present():
    keys = {"wikidata_qid", "ballotpedia-slug"}
    assert BallotpediaProvider().can_run(keys, {"ballotpedia"}) is True


def test_can_run_false_when_slug_absent():
    keys = {"wikidata_qid"}
    assert BallotpediaProvider().can_run(keys, {"ballotpedia"}) is False


def test_can_run_false_when_platform_inactive():
    keys = {"wikidata_qid", "ballotpedia-slug"}
    assert BallotpediaProvider().can_run(keys, set()) is False


# ---------------------------------------------------------------------------
# Core enrichment behaviour
# ---------------------------------------------------------------------------


def test_enrich_returns_ballotpedia_url():
    """ballotpedia_url is always present when page exists."""
    provider = _make_provider(response=_make_api_response(["Democratic Party", "California"]))
    results = provider.enrich(_person())
    url_result = next((r for r in results if r.key == "ballotpedia_url"), None)
    assert url_result is not None
    assert url_result.value == _BP_URL
    assert url_result.value_type == "platform_url"
    assert url_result.metadata == {"platform": "ballotpedia"}


def test_enrich_returns_ballotpedia_url_even_without_party():
    """ballotpedia_url is emitted even when no party category is found."""
    provider = _make_provider(response=_make_api_response(["Some Other Category"]))
    results = provider.enrich(_person())
    assert any(r.key == "ballotpedia_url" for r in results)


def test_enrich_extracts_party_from_democratic_category():
    provider = _make_provider(response=_make_api_response(["Democratic Party", "California"]))
    results = provider.enrich(_person())
    party_result = next((r for r in results if r.key == "party"), None)
    assert party_result is not None
    assert party_result.value == "Democratic Party"
    assert party_result.value_type == "text"


def test_enrich_extracts_party_from_republican_category():
    provider = _make_provider(response=_make_api_response(["Republican Party", "Texas"]))
    results = provider.enrich(_person())
    party_result = next((r for r in results if r.key == "party"), None)
    assert party_result is not None
    assert party_result.value == "Republican Party"


def test_enrich_no_party_when_no_matching_category():
    """Pages with no known party category produce only ballotpedia_url."""
    provider = _make_provider(response=_make_api_response(["Some Category", "Another Category"]))
    results = provider.enrich(_person())
    assert not any(r.key == "party" for r in results)
    assert any(r.key == "ballotpedia_url" for r in results)


def test_enrich_party_deterministic_when_multiple_party_categories():
    """When multiple party categories match, the alphabetically first is returned.

    Ballotpedia returns categories in alphabetical order.  Some politicians
    (e.g. independents who caucus with a party) carry both 'Independent' and
    'Democratic Party' categories.  The provider must pick consistently.
    """
    # API returns categories alphabetically: 'Democratic Party' < 'Independent'
    provider = _make_provider(response=_make_api_response(["Democratic Party", "Independent"]))
    results = provider.enrich(_person())
    party_result = next((r for r in results if r.key == "party"), None)
    assert party_result is not None
    assert party_result.value == "Democratic Party"


def test_enrich_calls_api_with_correct_params():
    provider = _make_provider(response=_make_api_response(["Democratic Party"]))
    provider.enrich(_person())
    call_kwargs = provider._session.get.call_args
    assert call_kwargs is not None
    called_url = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1].get("url", "")
    assert "ballotpedia.org" in called_url
    # Verify categories prop is requested
    params = call_kwargs[1].get("params", {})
    assert params.get("prop") == "categories"


# ---------------------------------------------------------------------------
# Skip-if-already-present logic
# ---------------------------------------------------------------------------


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
    provider = _make_provider(response=_make_api_response(["Democratic Party"]))
    results = provider.enrich(person)
    party_keys = [r for r in results if r.key == "party"]
    assert len(party_keys) == 0


# ---------------------------------------------------------------------------
# No-match paths
# ---------------------------------------------------------------------------


def test_no_match_when_slug_attribute_missing():
    provider = _make_provider(response=_make_api_response(["Democratic Party"]))
    with pytest.raises(NoMatchSignal):
        provider.enrich(_person_no_slug())


def test_no_match_when_page_missing():
    """MediaWiki API returns missing page marker → NoMatchSignal."""
    provider = _make_provider(response=_make_api_response(missing=True))
    with pytest.raises(NoMatchSignal):
        provider.enrich(_person())


def test_bpw_page_emits_url_not_no_match():
    """A page with BPW widgets (no infobox) but valid categories still emits ballotpedia_url."""
    # Simulates pages that have migrated to BPW widgets; no party category either.
    provider = _make_provider(response=_make_api_response(["Some Widget Category"]))
    # Should NOT raise NoMatchSignal
    results = provider.enrich(_person())
    assert any(r.key == "ballotpedia_url" for r in results)


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
    # Party should be extractable from Ballotpedia categories
    assert "party" in keys
    party_result = next(r for r in results if r.key == "party")
    assert "Democratic" in party_result.value
