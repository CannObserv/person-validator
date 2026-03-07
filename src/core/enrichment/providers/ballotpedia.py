"""BallotpediaProvider: US political figure enrichment via Ballotpedia MediaWiki API.

Round 3 provider. Depends on ``wikidata_qid`` and ``ballotpedia-slug`` attributes.
The ``ballotpedia-slug`` attribute (P2390 claim value) is written by WikidataProvider.

Note: P2390 is not imported by ``sync_wikidata_properties`` due to a structural SPARQL
filter limitation. It is seeded by migration 0015_seed_p2390_ballotpedia_property so that
WikidataProvider will extract and write the ballotpedia-slug attribute automatically.

Design notes:
  Ballotpedia has migrated all modern person pages from ``{{Infobox officeholder}}``
  wikitext templates to ``<BPW widget='profile/infobox' .../>`` widgets.  Because BPW
  widget content is rendered client-side and is not present in the MediaWiki API
  wikitext response, the infobox-parsing approach is no longer viable.

  Instead the provider fetches page *categories* (``prop=categories``) and extracts
  structured attributes from category membership:

  - ``ballotpedia_url`` — always emitted when the page exists.
  - ``party``           — inferred from party-name category (e.g. ``Democratic Party``).

  ``NoMatchSignal`` is raised only when:
  - The ``ballotpedia-slug`` attribute is absent from ``PersonData``.
  - The Ballotpedia page itself does not exist (MediaWiki ``missing`` marker).
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
from src.core.logging import get_logger

logger = get_logger(__name__)

_BALLOTPEDIA_CONFIDENCE: float = 0.90
_BASE_URL = "https://ballotpedia.org/wiki/api.php"
_USER_AGENT = "PersonValidator/0.1 (greg@cannabis.observer)"

# Known party category names on Ballotpedia.  Matched against the raw
# ``Category:<name>`` title returned by the API.
_PARTY_CATEGORIES: frozenset[str] = frozenset(
    [
        "Democratic Party",
        "Republican Party",
        "Libertarian Party",
        "Green Party",
        "Independent",
        "Democratic-Farmer-Labor Party",
        "Progressive Party",
        "Reform Party",
        "Constitution Party",
        "American Independent Party",
        "Peace and Freedom Party",
    ]
)


class BallotpediaProvider(Provider):
    """Enrich a person with their Ballotpedia page data.

    Depends on both ``wikidata_qid`` and ``ballotpedia-slug`` being present.
    The slug is the P2390 value extracted from Wikidata by WikidataProvider.

    Produces:
        - ``ballotpedia_url``  (``platform_url``, platform=``ballotpedia``)
        - ``party``            (``text``, inferred from Ballotpedia category membership)
    """

    name = "ballotpedia"
    output_keys = ["ballotpedia_url", "party"]
    refresh_interval = timedelta(days=1)
    dependencies = [
        Dependency("wikidata_qid", skip_if_absent=True),
        Dependency("ballotpedia-slug", skip_if_absent=True),
    ]
    required_platforms = ["ballotpedia"]

    def __init__(self) -> None:
        """Initialise with a shared requests.Session."""
        self._session = requests.Session()
        self._session.headers["User-Agent"] = _USER_AGENT

    def enrich(self, person: PersonData, **kwargs: object) -> list[EnrichmentResult]:  # noqa: ARG002
        """Fetch Ballotpedia page categories for *person* and emit structured attributes.

        Raises:
            NoMatchSignal: When ``ballotpedia-slug`` is absent or the page is missing.
        """
        # 1. Read ballotpedia-slug from existing attributes.
        slug = next(
            (a["value"] for a in person.existing_attributes if a["key"] == "ballotpedia-slug"),
            None,
        )
        if slug is None:
            raise NoMatchSignal("no ballotpedia-slug attribute present")

        # 2. Fetch categories from Ballotpedia MediaWiki API.
        response = self._session.get(
            _BASE_URL,
            params={
                "action": "query",
                "titles": slug,
                "prop": "categories",
                "cllimit": "500",
                "format": "json",
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        pages = data.get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        if "missing" in page:
            logger.info(
                "ballotpedia_provider.page_missing",
                extra={"slug": slug, "person_id": person.id},
            )
            raise NoMatchSignal(f"Ballotpedia page '{slug}' not found")

        # 3. Always emit ballotpedia_url — the page is confirmed to exist.
        bp_url = f"https://ballotpedia.org/{slug}"
        results: list[EnrichmentResult] = [
            EnrichmentResult(
                key="ballotpedia_url",
                value=bp_url,
                value_type="platform_url",
                confidence=_BALLOTPEDIA_CONFIDENCE,
                metadata={"platform": "ballotpedia"},
            )
        ]

        # 4. Extract party from category membership.
        existing_keys = person.attribute_keys()
        categories = {cat["title"].removeprefix("Category:") for cat in page.get("categories", [])}
        party = next((c for c in categories if c in _PARTY_CATEGORIES), None)
        if party and "party" not in existing_keys:
            results.append(
                EnrichmentResult(
                    key="party",
                    value=party,
                    value_type="text",
                    confidence=_BALLOTPEDIA_CONFIDENCE,
                )
            )

        if party is None:
            logger.info(
                "ballotpedia_provider.no_party_category",
                extra={"slug": slug, "person_id": person.id},
            )

        return results
