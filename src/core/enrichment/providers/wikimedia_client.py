"""Shared HTTP client for all Wikimedia API endpoints.

Handles User-Agent requirements, retry logic (429/503), and provides
typed methods for the Action API and SPARQL endpoint.
"""

import time
from typing import Any

import requests

from src.core.logging import get_logger

logger = get_logger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY = 1.0  # seconds
_RETRY_STATUSES = {429, 503}


class WikimediaHttpClient:
    """Shared HTTP client for all Wikimedia API endpoints.

    Sets the required User-Agent, handles retries on 429/503 with
    exponential backoff, and provides typed methods for the Action API
    and SPARQL endpoint.
    """

    BASE_URL = "https://www.wikidata.org/w/api.php"
    SPARQL_URL = "https://query.wikidata.org/sparql"
    USER_AGENT = "PersonValidator/0.1 (greg@cannabis.observer)"

    def __init__(self, session: requests.Session | None = None) -> None:
        """Initialise the client, optionally accepting a pre-configured session.

        Args:
            session: Optional ``requests.Session``.  When not provided a new
                session is created.  Injecting a session makes the client
                testable without real HTTP calls.
        """
        if session is None:
            session = requests.Session()
        session.headers.update({"User-Agent": self.USER_AGENT})
        self._session = session

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a GET request with retry logic for 429/503 responses."""
        delay = _BASE_DELAY
        # Total attempts = 1 initial + _MAX_RETRIES retries
        for attempt in range(1, _MAX_RETRIES + 2):
            response = self._session.get(url, params=params, timeout=30)
            if response.status_code not in _RETRY_STATUSES:
                response.raise_for_status()
                return response.json()
            if attempt > _MAX_RETRIES:
                response.raise_for_status()
            logger.warning(
                "Wikimedia API returned %s; retrying in %.1fs (attempt %d/%d)",
                response.status_code,
                delay,
                attempt,
                _MAX_RETRIES,
            )
            time.sleep(delay)
            delay *= 2
        # Unreachable; satisfy type checker.
        return {}  # pragma: no cover

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search_entities(self, name: str, limit: int = 10) -> list[dict]:
        """Search Wikidata for entities matching *name*.

        Uses the ``wbsearchentities`` Action API.  Does **not** filter by
        entity type; callers must confirm ``P31=Q5`` via :meth:`get_entities`.

        Args:
            name: The search string.
            limit: Maximum number of candidates to return (1–50).

        Returns:
            List of raw candidate dicts from the API response.
        """
        params = {
            "action": "wbsearchentities",
            "search": name,
            "language": "en",
            "type": "item",
            "limit": str(limit),
            "format": "json",
        }
        data = self._get(self.BASE_URL, params)
        return data.get("search", [])

    def get_entities(self, qids: list[str]) -> dict[str, dict]:
        """Batch-fetch full entity data for a list of QIDs.

        Wikidata supports up to 50 QIDs per request; callers are responsible
        for chunking larger lists if necessary.

        Args:
            qids: List of QIDs to fetch (e.g. ``["Q23", "Q42"]``).

        Returns:
            Dict mapping QID → entity dict (as returned by ``wbgetentities``).
            Missing/invalid QIDs are not included in the result.
        """
        if not qids:
            return {}
        params = {
            "action": "wbgetentities",
            "ids": "|".join(qids),
            "props": "labels|descriptions|aliases|claims|sitelinks",
            "languages": "en",
            "format": "json",
        }
        data = self._get(self.BASE_URL, params)
        entities = data.get("entities", {})
        # Filter out "missing" stubs (API returns {"id": "Q999", "missing": ""})
        return {qid: ent for qid, ent in entities.items() if "missing" not in ent}

    def get_wikipedia_summary(self, title: str) -> dict:
        """Fetch an English Wikipedia article summary via the REST API.

        Args:
            title: Article title as returned by the Wikidata ``enwiki`` sitelink
                (may contain underscores).

        Returns:
            The parsed JSON summary dict from the Wikimedia REST API.

        Raises:
            requests.HTTPError: For any HTTP error response (including 404).
                Callers should handle 404 as a "no article" signal.
        """
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
        return self._get(url, {})

    def sparql(self, query: str) -> list[dict]:
        """Execute a SPARQL SELECT query against the Wikidata query service.

        Args:
            query: SPARQL SELECT query string.

        Returns:
            List of result row dicts mapping variable names to simplified values.
            Each value is the ``value`` field from the SPARQL JSON binding.
        """
        params = {"query": query, "format": "json"}
        data = self._get(self.SPARQL_URL, params)
        bindings = data.get("results", {}).get("bindings", [])
        return [{k: v.get("value", "") for k, v in row.items()} for row in bindings]
