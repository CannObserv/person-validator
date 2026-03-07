"""WikidataProvider: search, disambiguate, link, and extract enrichment data.

Round 1 provider (no dependencies).  Searches Wikidata for a matching human
entity, scores candidates against existing person attributes, and either
auto-links the person or creates a WikidataCandidateReview for human review.
"""

from __future__ import annotations

from datetime import timedelta

from src.core.enrichment.base import (
    Dependency,
    EnrichmentResult,
    NoMatchSignal,
    PersonData,
    Provider,
)
from src.core.enrichment.name_utils import infer_name_type
from src.core.enrichment.providers.wikimedia_client import WikimediaHttpClient
from src.core.enrichment.wikidata_confidence import (
    ALIAS_CONFIDENCE as _ALIAS_CONFIDENCE,
)
from src.core.enrichment.wikidata_confidence import (
    AUTO_LINK_CONFIDENCE as _AUTO_LINK_CONFIDENCE,
)
from src.core.enrichment.wikidata_confidence import (
    AUTO_LINK_THRESHOLD as _AUTO_LINK_THRESHOLD,
)
from src.core.enrichment.wikidata_confidence import (
    CONFIRMED_ALIAS_CONFIDENCE as _CONFIRMED_ALIAS_CONFIDENCE,
)
from src.core.enrichment.wikidata_confidence import (
    CONFIRMED_CONFIDENCE as _CONFIRMED_CONFIDENCE,
)
from src.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Wikidata concept IDs
# ---------------------------------------------------------------------------

_HUMAN_QID = "Q5"
_DISAMBIGUATION_QID = "Q4167410"

# Wikidata property IDs
_P31_INSTANCE_OF = "P31"
_P569_BIRTH_DATE = "P569"
_P570_DEATH_DATE = "P570"
_P106_OCCUPATION = "P106"
_P27_COUNTRY_OF_CITIZENSHIP = "P27"

# Date precision values in Wikidata's data model
_PRECISION_DAY = 11
_PRECISION_YEAR = 9


# ---------------------------------------------------------------------------
# Entity parsing helpers
# ---------------------------------------------------------------------------


def _get_claim_qids(entity: dict, prop: str) -> list[str]:
    """Return all QID values for a given property in an entity's claims."""
    result = []
    for claim in entity.get("claims", {}).get(prop, []):
        try:
            qid = claim["mainsnak"]["datavalue"]["value"]["id"]
            result.append(qid)
        except (KeyError, TypeError):
            continue
    return result


def _get_claim_times(entity: dict, prop: str) -> list[dict]:
    """Return all time claim dicts for a given property (preserving precision)."""
    result = []
    for claim in entity.get("claims", {}).get(prop, []):
        try:
            dv = claim["mainsnak"]["datavalue"]
            if dv["type"] == "time":
                result.append(dv["value"])
        except (KeyError, TypeError):
            continue
    return result


def _parse_date(time_value: dict) -> tuple[str | None, str | None]:
    """Parse a Wikidata time value into (date_str, year_str).

    Returns:
        Tuple of (date_str, year_str) where:
        - date_str is YYYY-MM-DD if precision == day, else None
        - year_str is YYYY string if precision == year (and date_str is None)
        Both are None if precision < year.
    """
    time_str = time_value.get("time", "")
    precision = time_value.get("precision", 0)

    # Wikidata time format: +YYYY-MM-DDTHH:MM:SSZ (with possible leading zeros)
    # Negative years (BC dates) are not useful for our purposes.
    if time_str.startswith("-"):
        return None, None
    if time_str.startswith("+"):
        time_str = time_str[1:]

    try:
        year = int(time_str[:4])
    except (ValueError, IndexError):
        return None, None

    if year <= 0:
        return None, None

    if precision >= _PRECISION_DAY:
        # YYYY-MM-DD
        try:
            month = int(time_str[5:7])
            day = int(time_str[8:10])
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}", None
        except (ValueError, IndexError):
            pass
        return None, str(year)

    if precision == _PRECISION_YEAR:
        return None, str(year)

    return None, None


def _get_en_label(entity: dict) -> str:
    """Return the English label of an entity, or empty string."""
    return entity.get("labels", {}).get("en", {}).get("value", "")


def _get_en_description(entity: dict) -> str:
    """Return the English description of an entity, or empty string."""
    return entity.get("descriptions", {}).get("en", {}).get("value", "")


def _get_en_aliases(entity: dict) -> list[str]:
    """Return all English aliases for an entity."""
    return [a["value"] for a in entity.get("aliases", {}).get("en", [])]


def _is_human(entity: dict) -> bool:
    """Return True if the entity has P31=Q5 (instance of human)."""
    return _HUMAN_QID in _get_claim_qids(entity, _P31_INSTANCE_OF)


def _is_disambiguation_page(entity: dict) -> bool:
    """Return True if the entity is a disambiguation page (P31=Q4167410)."""
    return _DISAMBIGUATION_QID in _get_claim_qids(entity, _P31_INSTANCE_OF)


def _has_wikipedia_article(entity: dict) -> bool:
    """Return True if the entity has an English Wikipedia sitelink."""
    return "enwiki" in entity.get("sitelinks", {})


# ---------------------------------------------------------------------------
# Disambiguation scoring
# ---------------------------------------------------------------------------


def _score_candidate(
    entity: dict,
    person: PersonData,
    occupation_labels: dict[str, str],
    nationality_labels: dict[str, str],
) -> float:
    """Score a Wikidata entity candidate against a person's existing attributes.

    Returns a float in [0.0, 1.0].  The weights sum to 1.0:

    - Birth year match (±1 year): 0.35
    - Occupation keyword overlap:  0.25
    - Nationality/citizenship:     0.20
    - Name alias match:            0.15
    - Wikipedia article exists:    0.05
    """
    score = 0.0
    existing = person.existing_attributes

    # --- Birth year (0.35) ---
    birth_times = _get_claim_times(entity, _P569_BIRTH_DATE)
    if birth_times:
        date_str, year_str = _parse_date(birth_times[0])
        wd_year_str = date_str[:4] if date_str else year_str
        if wd_year_str:
            wd_year = int(wd_year_str)
            person_birth_values = [
                a["value"]
                for a in existing
                if "birth" in a.get("key", "").lower() and a.get("value_type") in ("date", "text")
            ]
            for pv in person_birth_values:
                try:
                    pv_year = int(str(pv)[:4])
                    if abs(pv_year - wd_year) <= 1:
                        score += 0.35
                        break
                except (ValueError, TypeError):
                    continue

    # --- Occupation (0.25) ---
    occ_qids = _get_claim_qids(entity, _P106_OCCUPATION)
    occ_labels_lower = {
        occupation_labels.get(qid, "").lower() for qid in occ_qids if qid in occupation_labels
    }
    if occ_labels_lower:
        text_values = " ".join(
            a["value"].lower() for a in existing if a.get("value_type") == "text"
        )
        if any(label and label in text_values for label in occ_labels_lower):
            score += 0.25

    # --- Nationality (0.20) ---
    nat_qids = _get_claim_qids(entity, _P27_COUNTRY_OF_CITIZENSHIP)
    nat_labels_lower = {
        nationality_labels.get(qid, "").lower() for qid in nat_qids if qid in nationality_labels
    }
    if nat_labels_lower:
        location_values = " ".join(
            a["value"].lower() for a in existing if a.get("value_type") == "location"
        )
        if any(label and label in location_values for label in nat_labels_lower):
            score += 0.20

    # --- Name alias match (0.15) ---
    aliases = {a.lower() for a in _get_en_aliases(entity)}
    aliases.add(_get_en_label(entity).lower())
    person_names_lower = {a["full_name"].lower() for a in existing if "full_name" in a}
    # Also check PersonData name fields directly
    for nm in (person.name, person.given_name, person.surname):
        if nm:
            person_names_lower.add(nm.lower())
    if aliases & person_names_lower:
        score += 0.15

    # --- Wikipedia article (0.05) ---
    if _has_wikipedia_article(entity):
        score += 0.05

    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class WikidataProvider(Provider):
    """Round 1 enrichment provider: searches and links Wikidata person entities.

    On a successful auto-link or confirmed-QID call, emits ``EnrichmentResult``
    objects for core biographical attributes, enabled external identifier
    properties, and English name aliases.

    When the search is ambiguous or all candidates score below the auto-link
    threshold, creates a ``WikidataCandidateReview`` for human adjudication
    (Django admin) and returns an empty list.
    """

    name = "wikidata"
    output_keys: list[str] = ["wikidata_qid", "wikidata_url"]
    refresh_interval: timedelta = timedelta(days=7)
    dependencies: list[Dependency] = []
    required_platforms: list[str] = ["wikidata"]

    # Class-level aliases — single source of truth lives in wikidata_confidence.py.
    AUTO_LINK_THRESHOLD: float = _AUTO_LINK_THRESHOLD
    AUTO_LINK_CONFIDENCE: float = _AUTO_LINK_CONFIDENCE
    CONFIRMED_CONFIDENCE: float = _CONFIRMED_CONFIDENCE
    ALIAS_CONFIDENCE: float = _ALIAS_CONFIDENCE
    CONFIRMED_ALIAS_CONFIDENCE: float = _CONFIRMED_ALIAS_CONFIDENCE

    def __init__(self, http_client: WikimediaHttpClient | None = None) -> None:
        """Initialise the provider, optionally injecting an HTTP client.

        Args:
            http_client: Shared :class:`WikimediaHttpClient`.  When ``None``
                a new default client is constructed.  Injection is required for
                unit tests that stub network calls.
        """
        self._client = http_client or WikimediaHttpClient()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def enrich(
        self,
        person: PersonData,
        *,
        confirmed_wikidata_qid: str | None = None,
        force_rescore: bool = False,
    ) -> list[EnrichmentResult]:
        """Run Wikidata enrichment for *person*.

        Three operating modes, evaluated in order:

        1. **Confirmed QID** (``confirmed_wikidata_qid`` set): skip search,
           extract the supplied QID at ``CONFIRMED_CONFIDENCE``.  Used after
           admin accepts a pending ``WikidataCandidateReview``.

        2. **Re-extract known QID** (``wikidata_qid`` already in
           ``existing_attributes``, no ``force_rescore``): re-fetch the known
           QID from the Wikidata API and call ``_extract()`` with the stored
           confidence.  No ``WikidataCandidateReview`` is created — the person
           is already identified.  This is the default refresh path.

        3. **Search** (no existing QID, or ``force_rescore=True``): run a fresh
           search/score cycle.  ``force_rescore`` discards any existing QID and
           forces a new search; used after admin rejects an auto-linked review.

        Args:
            person: Snapshot of the person record.
            confirmed_wikidata_qid: When set, use operating mode 1.
            force_rescore: When ``True``, use operating mode 3 regardless of
                whether a ``wikidata_qid`` attribute is already present.

        Returns:
            List of :class:`~src.core.enrichment.base.EnrichmentResult` objects.
            Empty when no match is found or a review is created for adjudication.
        """
        # Deferred import to avoid AppRegistryNotReady at module load time.
        from src.web.persons.models import (  # noqa: PLC0415
            ExternalIdentifierProperty,
            PersonName,
            WikidataCandidateReview,
        )

        confidence = self.AUTO_LINK_CONFIDENCE
        alias_confidence = self.ALIAS_CONFIDENCE

        if confirmed_wikidata_qid:
            # Mode 1 — confirmed path: skip search, extract directly.
            logger.info(
                "WikidataProvider: using confirmed QID",
                extra={"person_id": person.id, "qid": confirmed_wikidata_qid},
            )
            confidence = self.CONFIRMED_CONFIDENCE
            alias_confidence = self.CONFIRMED_ALIAS_CONFIDENCE
            entities = self._client.get_entities([confirmed_wikidata_qid])
            entity = entities.get(confirmed_wikidata_qid)
            if entity is None:
                logger.warning(
                    "WikidataProvider: confirmed QID not found",
                    extra={"person_id": person.id, "qid": confirmed_wikidata_qid},
                )
                return []
            return self._extract(
                person=person,
                entity=entity,
                qid=confirmed_wikidata_qid,
                confidence=confidence,
                alias_confidence=alias_confidence,
                PersonName=PersonName,
                ExternalIdentifierProperty=ExternalIdentifierProperty,
            )

        # Mode 2 — re-extract known QID (default refresh path).
        if not force_rescore:
            existing_attr = next(
                (a for a in person.existing_attributes if a.get("key") == "wikidata_qid"),
                None,
            )
            if existing_attr is not None:
                existing_qid = existing_attr["value"]
                if not existing_qid:
                    logger.warning(
                        "WikidataProvider: wikidata_qid attribute is empty; skipping re-extraction",
                        extra={"person_id": person.id},
                    )
                    return []
                existing_confidence = float(
                    existing_attr.get("confidence") or self.AUTO_LINK_CONFIDENCE
                )
                logger.info(
                    "WikidataProvider: re-extracting from known QID",
                    extra={"person_id": person.id, "qid": existing_qid},
                )
                entities = self._client.get_entities([existing_qid])
                entity = entities.get(existing_qid)
                if entity is None:
                    logger.warning(
                        "WikidataProvider: known QID not found during re-extraction",
                        extra={"person_id": person.id, "qid": existing_qid},
                    )
                    return []
                alias_confidence = (
                    self.CONFIRMED_ALIAS_CONFIDENCE
                    if existing_confidence >= self.CONFIRMED_CONFIDENCE - 1e-9
                    else self.ALIAS_CONFIDENCE
                )
                return self._extract(
                    person=person,
                    entity=entity,
                    qid=existing_qid,
                    confidence=existing_confidence,
                    alias_confidence=alias_confidence,
                    PersonName=PersonName,
                    ExternalIdentifierProperty=ExternalIdentifierProperty,
                )

        # Search path
        search_name = person.name
        candidates_raw = self._client.search_entities(search_name, limit=10)

        if not candidates_raw:
            logger.info(
                "WikidataProvider: no candidates returned",
                extra={"person_id": person.id, "search_name": search_name},
            )
            raise NoMatchSignal(f"No Wikidata candidates for {search_name!r}")

        # Batch-fetch entities to check P31 and gather scoring data.
        qids = [c["id"] for c in candidates_raw if "id" in c][:50]
        entities = self._client.get_entities(qids)

        # Filter to humans only (exclude disambiguation pages).
        human_entities = {
            qid: ent
            for qid, ent in entities.items()
            if _is_human(ent) and not _is_disambiguation_page(ent)
        }

        if not human_entities:
            logger.info(
                "WikidataProvider: no human candidates after filtering",
                extra={"person_id": person.id, "search_name": search_name},
            )
            raise NoMatchSignal(f"No human Wikidata candidates for {search_name!r}")

        # Resolve labels for scoring (occupation + nationality)
        occ_labels, nat_labels = self._fetch_scoring_labels(human_entities)

        # Score each candidate
        scored: list[tuple[float, str, dict]] = []
        for qid, entity in human_entities.items():
            score = _score_candidate(entity, person, occ_labels, nat_labels)
            scored.append((score, qid, entity))
        scored.sort(key=lambda t: t[0], reverse=True)

        # Build candidate dicts for review storage
        candidate_dicts = self._build_candidate_dicts(scored, occ_labels, nat_labels)

        top_score, top_qid, top_entity = scored[0]
        above_threshold = [(s, q, e) for s, q, e in scored if s >= self.AUTO_LINK_THRESHOLD]

        if top_score >= self.AUTO_LINK_THRESHOLD and len(above_threshold) == 1:
            # Auto-link path
            logger.info(
                "WikidataProvider: auto-linking person",
                extra={"person_id": person.id, "qid": top_qid, "score": top_score},
            )
            # Create auto_linked review (for #31 confirmation flow)
            WikidataCandidateReview.objects.create(
                person_id=person.id,
                query_name=search_name,
                candidates=candidate_dicts[:5],
                status="auto_linked",
                linked_qid=top_qid,
            )
            # Merge occ + nat labels into a single preloaded dict to avoid
            # redundant HTTP calls during extraction.
            preloaded = {**occ_labels, **nat_labels}
            return self._extract(
                person=person,
                entity=top_entity,
                qid=top_qid,
                confidence=confidence,
                alias_confidence=alias_confidence,
                PersonName=PersonName,
                ExternalIdentifierProperty=ExternalIdentifierProperty,
                preloaded_labels=preloaded,
            )

        # Ambiguous / below-threshold path: create pending review.
        logger.info(
            "WikidataProvider: creating pending review",
            extra={
                "person_id": person.id,
                "top_score": top_score,
                "candidate_count": len(scored),
            },
        )
        WikidataCandidateReview.objects.create(
            person_id=person.id,
            query_name=search_name,
            candidates=candidate_dicts[:5],
            status="pending",
        )
        return []

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def _extract(
        self,
        *,
        person: PersonData,
        entity: dict,
        qid: str,
        confidence: float,
        alias_confidence: float,
        PersonName: type,
        ExternalIdentifierProperty: type,
        preloaded_labels: dict[str, str] | None = None,
    ) -> list[EnrichmentResult]:
        """Extract EnrichmentResult objects from a confirmed Wikidata entity.

        Args:
            preloaded_labels: Optional dict mapping QID -> English label, used
                to resolve occupation and nationality labels without additional
                HTTP calls.  When provided (search path), labels fetched during
                scoring are reused.  When ``None`` (confirmed-QID path), labels
                are fetched on demand.
        """
        results: list[EnrichmentResult] = []

        # --- Core link attributes ---
        results.append(
            EnrichmentResult(
                key="wikidata_qid", value=qid, value_type="text", confidence=confidence
            )
        )
        results.append(
            EnrichmentResult(
                key="wikidata_url",
                value=f"https://www.wikidata.org/wiki/{qid}",
                value_type="platform_url",
                confidence=confidence,
                metadata={"platform": "wikidata"},
            )
        )

        # --- Description ---
        description = _get_en_description(entity)
        if description:
            results.append(
                EnrichmentResult(
                    key="description", value=description, value_type="text", confidence=confidence
                )
            )

        # --- Birth date / year ---
        birth_times = _get_claim_times(entity, _P569_BIRTH_DATE)
        if birth_times:
            date_str, year_str = _parse_date(birth_times[0])
            if date_str:
                results.append(
                    EnrichmentResult(
                        key="birth_date", value=date_str, value_type="date", confidence=confidence
                    )
                )
            elif year_str:
                results.append(
                    EnrichmentResult(
                        key="birth_year", value=year_str, value_type="text", confidence=confidence
                    )
                )

        # --- Death date / year ---
        death_times = _get_claim_times(entity, _P570_DEATH_DATE)
        if death_times:
            date_str, year_str = _parse_date(death_times[0])
            if date_str:
                results.append(
                    EnrichmentResult(
                        key="death_date", value=date_str, value_type="date", confidence=confidence
                    )
                )
            elif year_str:
                results.append(
                    EnrichmentResult(
                        key="death_year", value=year_str, value_type="text", confidence=confidence
                    )
                )

        # --- Occupations ---
        occ_qids = _get_claim_qids(entity, _P106_OCCUPATION)
        if occ_qids:
            labels = self._resolve_labels(occ_qids, preloaded_labels)
            for occ_qid in occ_qids:
                label = labels.get(occ_qid, "")
                if label:
                    results.append(
                        EnrichmentResult(
                            key="occupation",
                            value=label,
                            value_type="text",
                            confidence=confidence,
                        )
                    )

        # --- Nationality ---
        nat_qids = _get_claim_qids(entity, _P27_COUNTRY_OF_CITIZENSHIP)
        if nat_qids:
            labels = self._resolve_labels(nat_qids, preloaded_labels)
            for nat_qid in nat_qids:
                label = labels.get(nat_qid, "")
                if label:
                    results.append(
                        EnrichmentResult(
                            key="nationality",
                            value=label,
                            value_type="text",
                            confidence=confidence,
                        )
                    )

        # --- External identifiers ---
        results.extend(
            self._extract_external_identifiers(
                entity=entity,
                confidence=confidence,
                ExternalIdentifierProperty=ExternalIdentifierProperty,
            )
        )

        # --- Name aliases ---
        self._create_aliases(
            person=person,
            entity=entity,
            qid=qid,
            alias_confidence=alias_confidence,
            PersonName=PersonName,
        )

        return results

    def _extract_external_identifiers(
        self,
        *,
        entity: dict,
        confidence: float,
        ExternalIdentifierProperty: type,
    ) -> list[EnrichmentResult]:
        """Emit EnrichmentResults for enabled ExternalIdentifierProperty records.

        For each enabled property found on the entity:
        - If the property has a ``formatter_url`` and a linked ``ExternalPlatform``
          FK, emit a ``platform_url`` attribute.
        - If the property has a ``formatter_url`` but no ``ExternalPlatform`` FK,
          the identifier is skipped with a warning (platform must be configured
          explicitly; auto-creation is not allowed).
        - If the property has no ``formatter_url``, emit the raw identifier as a
          ``text`` attribute.
        """
        results: list[EnrichmentResult] = []
        claims = entity.get("claims", {})

        # Fetch all enabled properties in one query
        enabled_props = {
            prop.wikidata_property_id: prop
            for prop in ExternalIdentifierProperty.objects.filter(is_enabled=True).select_related(
                "platform"
            )
        }

        for prop_id, prop in enabled_props.items():
            if prop_id not in claims:
                continue
            # Get the identifier value (string type)
            for claim in claims[prop_id]:
                try:
                    dv = claim["mainsnak"]["datavalue"]
                    if dv["type"] != "string":
                        continue
                    identifier_value = dv["value"]
                except (KeyError, TypeError):
                    continue

                url = prop.build_url(identifier_value)
                if url:
                    if prop.platform is None:
                        logger.warning(
                            "WikidataProvider: skipping platform_url for '%s' "
                            "(property has formatter_url but no ExternalPlatform FK; "
                            "configure the platform via Django admin)",
                            prop.slug,
                        )
                    else:
                        results.append(
                            EnrichmentResult(
                                key=prop.slug,
                                value=url,
                                value_type="platform_url",
                                confidence=confidence,
                                metadata={"platform": prop.platform.slug},
                            )
                        )
                else:
                    # No formatter_url — emit raw identifier as text
                    results.append(
                        EnrichmentResult(
                            key=prop.slug,
                            value=identifier_value,
                            value_type="text",
                            confidence=confidence,
                        )
                    )
                # Only take the first value per property
                break

        return results

    def _create_aliases(
        self,
        *,
        person: PersonData,
        entity: dict,
        qid: str,
        alias_confidence: float,
        PersonName: type,
    ) -> None:
        """Create PersonName records for English aliases not already on the person."""
        from django.utils import timezone  # noqa: PLC0415

        aliases = _get_en_aliases(entity)
        existing_names = set(
            PersonName.objects.filter(person_id=person.id).values_list("full_name", flat=True)
        )

        for alias in aliases:
            if alias in existing_names:
                continue
            name_type = infer_name_type(alias, person.name)
            PersonName.objects.create(
                person_id=person.id,
                full_name=alias,
                name_type=name_type,
                is_primary=False,
                source="wikidata",
                confidence=alias_confidence,
                provenance={
                    "provider": "wikidata",
                    "wikidata_qid": qid,
                    "wikidata_alias_lang": "en",
                    "retrieved_at": timezone.now().isoformat(),
                },
            )
            existing_names.add(alias)

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _resolve_labels(
        self,
        qids: list[str],
        preloaded: dict[str, str] | None,
    ) -> dict[str, str]:
        """Return a QID -> English label mapping for *qids*.

        Uses *preloaded* (the scoring-phase label cache) when available to
        avoid additional HTTP calls.  Falls back to fetching any QIDs absent
        from the cache, chunking at 50 per Wikidata API request.
        """
        if preloaded is not None:
            missing = [q for q in qids if q not in preloaded]
            if not missing:
                return {q: preloaded[q] for q in qids if q in preloaded}
            # Fetch only the QIDs not already in the cache
            fetched: dict[str, str] = {}
            for i in range(0, len(missing), 50):
                chunk_entities = self._client.get_entities(missing[i : i + 50])
                for qid, ent in chunk_entities.items():
                    fetched[qid] = _get_en_label(ent)
            combined = {**preloaded, **fetched}
            return {q: combined[q] for q in qids if q in combined}

        # No preloaded cache — fetch all
        result: dict[str, str] = {}
        for i in range(0, len(qids), 50):
            chunk_entities = self._client.get_entities(qids[i : i + 50])
            for qid, ent in chunk_entities.items():
                result[qid] = _get_en_label(ent)
        return result

    def _fetch_scoring_labels(
        self,
        human_entities: dict[str, dict],
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Batch-fetch English labels for occupation and nationality QIDs.

        Fetches all required QIDs in chunks of 50 (Wikidata API limit per
        request) so that large candidate sets with many distinct occupation
        or nationality QIDs are fully resolved.

        Returns:
            Tuple of (occupation_labels, nationality_labels) where each is a
            dict mapping QID -> English label string.
        """
        occ_qids: set[str] = set()
        nat_qids: set[str] = set()
        for entity in human_entities.values():
            occ_qids.update(_get_claim_qids(entity, _P106_OCCUPATION))
            nat_qids.update(_get_claim_qids(entity, _P27_COUNTRY_OF_CITIZENSHIP))

        all_qids = list(occ_qids | nat_qids)
        if not all_qids:
            return {}, {}

        labels: dict[str, str] = {}
        for i in range(0, len(all_qids), 50):
            chunk = all_qids[i : i + 50]
            chunk_entities = self._client.get_entities(chunk)
            for qid, ent in chunk_entities.items():
                labels[qid] = _get_en_label(ent)

        occ_labels = {qid: labels[qid] for qid in occ_qids if qid in labels}
        nat_labels = {qid: labels[qid] for qid in nat_qids if qid in labels}
        return occ_labels, nat_labels

    def _build_candidate_dicts(
        self,
        scored: list[tuple[float, str, dict]],
        occ_labels: dict[str, str],
        nat_labels: dict[str, str],
    ) -> list[dict]:
        """Build the candidate dicts stored in WikidataCandidateReview.candidates."""
        result = []
        for score, qid, entity in scored:
            birth_times = _get_claim_times(entity, _P569_BIRTH_DATE)
            birth_date, birth_year = _parse_date(birth_times[0]) if birth_times else (None, None)
            death_times = _get_claim_times(entity, _P570_DEATH_DATE)
            death_date, death_year = _parse_date(death_times[0]) if death_times else (None, None)

            occ_qids = _get_claim_qids(entity, _P106_OCCUPATION)
            occupations = [occ_labels[q] for q in occ_qids if q in occ_labels]

            nat_qids = _get_claim_qids(entity, _P27_COUNTRY_OF_CITIZENSHIP)
            nationality = next((nat_labels[q] for q in nat_qids if q in nat_labels), None)

            sitelinks = entity.get("sitelinks", {})
            enwiki = sitelinks.get("enwiki", {})
            wikipedia_url = (
                f"https://en.wikipedia.org/wiki/{enwiki['title']}" if enwiki.get("title") else None
            )

            result.append(
                {
                    "qid": qid,
                    "label": _get_en_label(entity),
                    "description": _get_en_description(entity),
                    "score": round(score, 4),
                    "wikipedia_url": wikipedia_url,
                    "extract": None,
                    "properties": {
                        "birth_date": birth_date,
                        "birth_year": birth_year,
                        "death_date": death_date,
                        "death_year": death_year,
                        "occupations": occupations,
                        "nationality": nationality,
                        "image_url": None,
                    },
                }
            )
        return result
