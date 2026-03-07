"""WikipediaProvider: article URL and summary extract enrichment.

Round 2 provider (depends on ``wikidata_qid`` written by WikidataProvider).
Fetches the English Wikipedia article for the person via the Wikidata
enwiki sitelink and extracts the article URL and plain-text summary.
"""

from __future__ import annotations

from datetime import timedelta

import requests

from src.core.enrichment.base import (
    Dependency,
    EnrichmentResult,
    NoMatchSignal,
    PersonData,
    Provider,
)
from src.core.enrichment.providers.wikimedia_client import WikimediaHttpClient
from src.core.logging import get_logger

logger = get_logger(__name__)

_WIKIPEDIA_CONFIDENCE: float = 0.90


class WikipediaProvider(Provider):
    """Enrich a person with their English Wikipedia article URL and summary.

    Depends on ``wikidata_qid`` being present (written by WikidataProvider).
    Uses the Wikidata entity's ``enwiki`` sitelink to locate the article, then
    fetches the plain-text extract from the Wikimedia REST API.

    Produces:
        - ``wikipedia_url``    (``platform_url``, platform=``wikipedia``)
        - ``wikipedia_extract``(``text``)
    """

    name = "wikipedia"
    output_keys = ["wikipedia_url", "wikipedia_extract"]
    refresh_interval = timedelta(days=7)
    dependencies = [
        Dependency("wikidata_qid", skip_if_absent=True),
    ]
    required_platforms = ["wikipedia"]

    def __init__(self, client: WikimediaHttpClient | None = None) -> None:
        """Initialise the provider.

        Args:
            client: Optional shared :class:`WikimediaHttpClient` instance.
                When not provided a new client with default settings is created.
                Inject a mock client in tests.
        """
        self._client = client if client is not None else WikimediaHttpClient()

    def enrich(self, person: PersonData, **kwargs: object) -> list[EnrichmentResult]:  # noqa: ARG002
        """Return Wikipedia URL and extract for *person*.

        Raises:
            NoMatchSignal: When no ``wikidata_qid`` attribute is found, the
                entity has no English Wikipedia article, or the article returns
                HTTP 404.
        """
        # 1. Read wikidata_qid from existing attributes.
        qid = next(
            (a["value"] for a in person.existing_attributes if a["key"] == "wikidata_qid"),
            None,
        )
        if qid is None:
            raise NoMatchSignal("no wikidata_qid attribute present")

        # 2. Fetch the Wikidata entity to get the enwiki sitelink.
        entities = self._client.get_entities([qid])
        entity = entities.get(qid)
        if entity is None:
            logger.warning("wikipedia_provider.entity_not_found", extra={"qid": qid})
            raise NoMatchSignal(f"Wikidata entity {qid} not found")

        sitelinks = entity.get("sitelinks", {})
        enwiki = sitelinks.get("enwiki", {})
        title = enwiki.get("title") if enwiki else None
        if not title:
            logger.info(
                "wikipedia_provider.no_enwiki_sitelink",
                extra={"qid": qid, "person_id": person.id},
            )
            raise NoMatchSignal(f"No English Wikipedia article for {qid}")

        # 3. Fetch the article summary from the Wikimedia REST API.
        # Normalise title to use underscores for the URL path.
        url_title = title.replace(" ", "_")
        try:
            summary = self._client.get_wikipedia_summary(url_title)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.warning(
                    "wikipedia_provider.article_not_found",
                    extra={"qid": qid, "title": url_title, "person_id": person.id},
                )
                raise NoMatchSignal(f"Wikipedia article '{url_title}' returned 404") from exc
            raise

        # 4. Build results.
        article_url = f"https://en.wikipedia.org/wiki/{url_title}"
        extract = summary.get("extract", "")

        return [
            EnrichmentResult(
                key="wikipedia_url",
                value=article_url,
                value_type="platform_url",
                confidence=_WIKIPEDIA_CONFIDENCE,
                metadata={"platform": "wikipedia"},
            ),
            EnrichmentResult(
                key="wikipedia_extract",
                value=extract,
                value_type="text",
                confidence=_WIKIPEDIA_CONFIDENCE,
            ),
        ]
