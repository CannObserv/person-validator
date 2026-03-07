"""BallotpediaProvider: US political figure enrichment via Ballotpedia MediaWiki API.

Round 3 provider. Depends on ``wikidata_qid`` and ``ballotpedia-slug`` attributes.
The ``ballotpedia-slug`` attribute (P2390 claim value) is written by WikidataProvider.

Note: P2390 is not imported by ``sync_wikidata_properties`` due to a structural SPARQL
filter limitation. It is seeded by migration 0015_seed_p2390_ballotpedia_property so that
WikidataProvider will extract and write the ballotpedia-slug attribute automatically.
"""

from __future__ import annotations

from datetime import timedelta

import mwparserfromhell
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
_BASE_URL = "https://ballotpedia.org/api.php"
_USER_AGENT = "PersonValidator/0.1 (greg@cannabis.observer)"


def _parse_birth_date(birth_date_str: str) -> str | None:
    """Extract ISO 8601 date from a {{birth date|...}} or {{birth date and age|...}} template.

    Returns YYYY-MM-DD string or None if unparseable.
    """
    try:
        wikicode = mwparserfromhell.parse(birth_date_str)
        for template in wikicode.filter_templates():
            tname = template.name.strip().lower()
            if "birth date" in tname:
                try:
                    year = template.get(1).value.strip()
                    month = template.get(2).value.strip()
                    day = template.get(3).value.strip()
                    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
                except (ValueError, KeyError):
                    continue
    except Exception:  # noqa: BLE001
        pass
    # Fall back: try plain YYYY-MM-DD
    stripped = birth_date_str.strip()
    if len(stripped) == 10 and stripped[4] == "-" and stripped[7] == "-":
        return stripped
    return None


class BallotpediaProvider(Provider):
    """Enrich a person with their Ballotpedia page data.

    Depends on both ``wikidata_qid`` and ``ballotpedia-slug`` being present.
    The slug is the P2390 value extracted from Wikidata by WikidataProvider.

    Produces:
        - ``ballotpedia_url``  (``platform_url``, platform=``ballotpedia``)
        - ``party``            (``text``)
        - ``office_held``      (``text``, one per office)
        - ``state``            (``text``)
        - ``birth_date``       (``date``, skipped if already present)
    """

    name = "ballotpedia"
    output_keys = ["ballotpedia_url", "party", "office_held", "state"]
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
        """Fetch and parse Ballotpedia page for *person*.

        Raises:
            NoMatchSignal: When ``ballotpedia-slug`` is absent, the page is
                missing, or the page has no officeholder infobox.
        """
        # 1. Read ballotpedia-slug from existing attributes.
        slug = next(
            (a["value"] for a in person.existing_attributes if a["key"] == "ballotpedia-slug"),
            None,
        )
        if slug is None:
            raise NoMatchSignal("no ballotpedia-slug attribute present")

        # 2. Fetch wikitext from Ballotpedia MediaWiki API.
        response = self._session.get(
            _BASE_URL,
            params={
                "action": "query",
                "titles": slug,
                "prop": "revisions",
                "rvprop": "content",
                "format": "json",
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        pages = data.get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        if "missing" in page or page.get("pageid") is None and "missing" in page:
            logger.info(
                "ballotpedia_provider.page_missing",
                extra={"slug": slug, "person_id": person.id},
            )
            raise NoMatchSignal(f"Ballotpedia page '{slug}' not found")

        revisions = page.get("revisions", [])
        if not revisions:
            raise NoMatchSignal(f"Ballotpedia page '{slug}' has no revisions")

        wikitext = revisions[0].get("*", "")

        # 3. Parse wikitext and extract officeholder infobox.
        wikicode = mwparserfromhell.parse(wikitext)
        templates = wikicode.filter_templates()
        infobox = next(
            (t for t in templates if "officeholder" in t.name.strip().lower()),
            None,
        )
        if infobox is None:
            logger.info(
                "ballotpedia_provider.no_officeholder_infobox",
                extra={"slug": slug, "person_id": person.id},
            )
            raise NoMatchSignal(f"Ballotpedia page '{slug}' has no officeholder infobox")

        existing_keys = person.attribute_keys()
        results: list[EnrichmentResult] = []

        # 4. Always emit ballotpedia_url.
        bp_url = f"https://ballotpedia.org/{slug}"
        results.append(
            EnrichmentResult(
                key="ballotpedia_url",
                value=bp_url,
                value_type="platform_url",
                confidence=_BALLOTPEDIA_CONFIDENCE,
                metadata={"platform": "ballotpedia"},
            )
        )

        # 5. Extract optional infobox fields (skip if already present).
        def _get(field: str) -> str | None:
            try:
                return infobox.get(field).value.strip()
            except ValueError:
                return None

        party = _get("party")
        if party and "party" not in existing_keys:
            # Strip wikitext markup from party value
            plain_party = mwparserfromhell.parse(party).strip_code().strip()
            if plain_party:
                results.append(
                    EnrichmentResult(
                        key="party",
                        value=plain_party,
                        value_type="text",
                        confidence=_BALLOTPEDIA_CONFIDENCE,
                    )
                )

        state = _get("state")
        if state and "state" not in existing_keys:
            plain_state = mwparserfromhell.parse(state).strip_code().strip()
            if plain_state:
                results.append(
                    EnrichmentResult(
                        key="state",
                        value=plain_state,
                        value_type="text",
                        confidence=_BALLOTPEDIA_CONFIDENCE,
                    )
                )

        office = _get("office")
        if office and "office_held" not in existing_keys:
            plain_office = mwparserfromhell.parse(office).strip_code().strip()
            if plain_office:
                results.append(
                    EnrichmentResult(
                        key="office_held",
                        value=plain_office,
                        value_type="text",
                        confidence=_BALLOTPEDIA_CONFIDENCE,
                    )
                )

        birth_date_raw = _get("birth_date")
        if birth_date_raw and "birth_date" not in existing_keys:
            parsed_date = _parse_birth_date(birth_date_raw)
            if parsed_date:
                results.append(
                    EnrichmentResult(
                        key="birth_date",
                        value=parsed_date,
                        value_type="date",
                        confidence=_BALLOTPEDIA_CONFIDENCE,
                    )
                )

        return results
