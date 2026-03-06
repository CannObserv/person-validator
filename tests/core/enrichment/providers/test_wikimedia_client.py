"""Tests for WikimediaHttpClient."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.core.enrichment.providers.wikimedia_client import WikimediaHttpClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    return resp


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestWikimediaHttpClientInit:
    """Tests for client initialization."""

    def test_sets_user_agent_on_session(self):
        """The required User-Agent header is set on the underlying session."""
        client = WikimediaHttpClient()
        assert client._session.headers.get("User-Agent") == WikimediaHttpClient.USER_AGENT

    def test_accepts_injected_session(self):
        """An injected session is used directly."""
        session = requests.Session()
        client = WikimediaHttpClient(session=session)
        assert client._session is session

    def test_injected_session_gets_user_agent(self):
        """User-Agent is applied even to an injected session."""
        session = requests.Session()
        WikimediaHttpClient(session=session)
        assert session.headers.get("User-Agent") == WikimediaHttpClient.USER_AGENT


# ---------------------------------------------------------------------------
# search_entities
# ---------------------------------------------------------------------------


class TestSearchEntities:
    """Tests for WikimediaHttpClient.search_entities."""

    def test_returns_search_results(self):
        """Returns the list of candidates from the search response."""
        mock_resp = _mock_response({"search": [{"id": "Q23", "label": "George Washington"}]})
        session = MagicMock()
        session.get.return_value = mock_resp
        session.headers = {}
        client = WikimediaHttpClient(session=session)

        result = client.search_entities("George Washington")

        assert result == [{"id": "Q23", "label": "George Washington"}]

    def test_passes_correct_params(self):
        """The correct Action API parameters are sent."""
        mock_resp = _mock_response({"search": []})
        session = MagicMock()
        session.get.return_value = mock_resp
        session.headers = {}
        client = WikimediaHttpClient(session=session)

        client.search_entities("Ada Lovelace", limit=5)

        _, kwargs = session.get.call_args
        params = kwargs["params"]
        assert params["action"] == "wbsearchentities"
        assert params["search"] == "Ada Lovelace"
        assert params["limit"] == "5"
        assert params["language"] == "en"

    def test_returns_empty_list_on_no_results(self):
        """Returns an empty list when the API response has no 'search' key."""
        mock_resp = _mock_response({})
        session = MagicMock()
        session.get.return_value = mock_resp
        session.headers = {}
        client = WikimediaHttpClient(session=session)

        result = client.search_entities("Unknown Entity")

        assert result == []


# ---------------------------------------------------------------------------
# get_entities
# ---------------------------------------------------------------------------


class TestGetEntities:
    """Tests for WikimediaHttpClient.get_entities."""

    def test_returns_entity_dict(self):
        """Returns a dict mapping QID to entity data."""
        entity_data = {"id": "Q23", "labels": {"en": {"value": "George Washington"}}}
        mock_resp = _mock_response({"entities": {"Q23": entity_data}})
        session = MagicMock()
        session.get.return_value = mock_resp
        session.headers = {}
        client = WikimediaHttpClient(session=session)

        result = client.get_entities(["Q23"])

        assert "Q23" in result
        assert result["Q23"] == entity_data

    def test_pipes_multiple_qids(self):
        """Multiple QIDs are joined with '|' in the ids parameter."""
        mock_resp = _mock_response({"entities": {}})
        session = MagicMock()
        session.get.return_value = mock_resp
        session.headers = {}
        client = WikimediaHttpClient(session=session)

        client.get_entities(["Q23", "Q42"])

        _, kwargs = session.get.call_args
        assert kwargs["params"]["ids"] == "Q23|Q42"

    def test_empty_qids_returns_empty(self):
        """Returns empty dict without making an HTTP call when qids is empty."""
        session = MagicMock()
        session.headers = {}
        client = WikimediaHttpClient(session=session)

        result = client.get_entities([])

        assert result == {}
        session.get.assert_not_called()

    def test_filters_missing_entities(self):
        """Entities with a 'missing' key are excluded from the result."""
        mock_resp = _mock_response(
            {
                "entities": {
                    "Q23": {"id": "Q23", "labels": {}},
                    "Q99999": {"id": "Q99999", "missing": ""},
                }
            }
        )
        session = MagicMock()
        session.get.return_value = mock_resp
        session.headers = {}
        client = WikimediaHttpClient(session=session)

        result = client.get_entities(["Q23", "Q99999"])

        assert "Q23" in result
        assert "Q99999" not in result


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


class TestRetryLogic:
    """Tests for 429/503 retry behaviour."""

    def test_retries_on_429(self):
        """A 429 response triggers a retry and succeeds on the second attempt."""
        success_resp = _mock_response({"search": [{"id": "Q1"}]})
        throttle_resp = _mock_response({}, status_code=429)

        session = MagicMock()
        session.get.side_effect = [throttle_resp, success_resp]
        session.headers = {}
        client = WikimediaHttpClient(session=session)

        with patch("src.core.enrichment.providers.wikimedia_client.time.sleep") as mock_sleep:
            result = client.search_entities("Test")

        assert result == [{"id": "Q1"}]
        assert session.get.call_count == 2
        mock_sleep.assert_called_once()

    def test_retries_on_503(self):
        """A 503 response triggers a retry."""
        success_resp = _mock_response({"search": []})
        error_resp = _mock_response({}, status_code=503)

        session = MagicMock()
        session.get.side_effect = [error_resp, success_resp]
        session.headers = {}
        client = WikimediaHttpClient(session=session)

        with patch("src.core.enrichment.providers.wikimedia_client.time.sleep"):
            client.search_entities("Test")

        assert session.get.call_count == 2

    def test_raises_after_max_retries(self):
        """Raises HTTPError after MAX_RETRIES+1 failed attempts."""
        throttle_resp = _mock_response({}, status_code=429)
        throttle_resp.raise_for_status.side_effect = requests.HTTPError(response=throttle_resp)

        session = MagicMock()
        session.get.return_value = throttle_resp
        session.headers = {}
        client = WikimediaHttpClient(session=session)

        with patch("src.core.enrichment.providers.wikimedia_client.time.sleep"):
            with pytest.raises(requests.HTTPError):
                client.search_entities("Test")


# ---------------------------------------------------------------------------
# sparql
# ---------------------------------------------------------------------------


class TestSparql:
    """Tests for WikimediaHttpClient.sparql."""

    def test_returns_simplified_bindings(self):
        """Returns a list of dicts with simplified binding values."""
        sparql_resp = {
            "results": {
                "bindings": [
                    {"item": {"type": "uri", "value": "http://www.wikidata.org/entity/Q23"}}
                ]
            }
        }
        mock_resp = _mock_response(sparql_resp)
        session = MagicMock()
        session.get.return_value = mock_resp
        session.headers = {}
        client = WikimediaHttpClient(session=session)

        result = client.sparql("SELECT ?item WHERE { ?item wdt:P31 wd:Q5 }")

        assert result == [{"item": "http://www.wikidata.org/entity/Q23"}]

    def test_returns_empty_on_no_results(self):
        """Returns empty list when no SPARQL results."""
        mock_resp = _mock_response({"results": {"bindings": []}})
        session = MagicMock()
        session.get.return_value = mock_resp
        session.headers = {}
        client = WikimediaHttpClient(session=session)

        result = client.sparql("SELECT ?x WHERE { }")

        assert result == []
