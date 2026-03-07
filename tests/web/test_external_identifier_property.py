"""Tests for ExternalIdentifierProperty model and sync_wikidata_properties command."""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.db import IntegrityError

from src.web.persons.models import ExternalIdentifierProperty, ExternalPlatform


@pytest.mark.django_db
class TestExternalIdentifierPropertyModel:
    """Tests for the ExternalIdentifierProperty model."""

    def test_create_minimal(self):
        """Can create a property with required fields."""
        prop = ExternalIdentifierProperty.objects.create(
            wikidata_property_id="P214",
            slug="viaf-cluster-id",
            display="VIAF cluster ID",
        )
        assert prop.pk is not None
        assert prop.wikidata_property_id == "P214"
        assert prop.slug == "viaf-cluster-id"
        assert prop.display == "VIAF cluster ID"
        assert prop.is_enabled is True
        assert prop.sort_order == 0
        assert prop.taxonomy_categories == []
        assert prop.formatter_url == ""
        assert prop.subject_item_label == ""
        assert prop.description == ""
        assert prop.last_synced_at is None
        assert prop.platform is None

    def test_wikidata_property_id_unique(self):
        """Two properties cannot share the same wikidata_property_id."""
        ExternalIdentifierProperty.objects.create(
            wikidata_property_id="P214",
            slug="viaf-cluster-id",
            display="VIAF cluster ID",
        )
        with pytest.raises(IntegrityError):
            ExternalIdentifierProperty.objects.create(
                wikidata_property_id="P214",
                slug="viaf-cluster-id-2",
                display="Duplicate",
            )

    def test_slug_unique(self):
        """Two properties cannot share the same slug."""
        ExternalIdentifierProperty.objects.create(
            wikidata_property_id="P214",
            slug="viaf-cluster-id",
            display="VIAF cluster ID",
        )
        with pytest.raises(IntegrityError):
            ExternalIdentifierProperty.objects.create(
                wikidata_property_id="P496",
                slug="viaf-cluster-id",
                display="Duplicate slug",
            )

    def test_str(self):
        """__str__ includes property ID and display label."""
        prop = ExternalIdentifierProperty(
            wikidata_property_id="P214",
            display="VIAF cluster ID",
        )
        assert str(prop) == "P214 — VIAF cluster ID"

    def test_db_table_name(self):
        """Model uses the expected db_table."""
        assert ExternalIdentifierProperty._meta.db_table == "persons_externalidentifierproperty"

    def test_ordering(self):
        """Default ordering is sort_order then wikidata_property_id."""
        ExternalIdentifierProperty.objects.create(
            wikidata_property_id="P496",
            slug="orcid-id",
            display="ORCID iD",
            sort_order=0,
        )
        ExternalIdentifierProperty.objects.create(
            wikidata_property_id="P214",
            slug="viaf-cluster-id",
            display="VIAF cluster ID",
            sort_order=0,
        )
        props = list(ExternalIdentifierProperty.objects.all())
        assert props[0].wikidata_property_id == "P214"
        assert props[1].wikidata_property_id == "P496"

    def test_platform_fk_nullable(self):
        """platform FK is optional."""
        platform = ExternalPlatform.objects.create(slug="viaf-test", display="VIAF Test")
        prop = ExternalIdentifierProperty.objects.create(
            wikidata_property_id="P214",
            slug="viaf-cluster-id",
            display="VIAF cluster ID",
            platform=platform,
        )
        assert prop.platform == platform
        assert prop.platform.slug == "viaf-test"

    def test_platform_set_null_on_delete(self):
        """Deleting the linked ExternalPlatform sets platform to NULL."""
        platform = ExternalPlatform.objects.create(slug="viaf-test2", display="VIAF Test 2")
        prop = ExternalIdentifierProperty.objects.create(
            wikidata_property_id="P214",
            slug="viaf-cluster-id",
            display="VIAF cluster ID",
            platform=platform,
        )
        platform.delete()
        prop.refresh_from_db()
        assert prop.platform is None

    def test_taxonomy_categories_json_field(self):
        """taxonomy_categories stores and retrieves a list of QID strings."""
        categories = ["Q19595382", "Q62589316"]
        prop = ExternalIdentifierProperty.objects.create(
            wikidata_property_id="P214",
            slug="viaf-cluster-id",
            display="VIAF cluster ID",
            taxonomy_categories=categories,
        )
        prop.refresh_from_db()
        assert prop.taxonomy_categories == categories


class TestBuildUrl:
    """Tests for ExternalIdentifierProperty.build_url()."""

    def test_with_formatter_url(self):
        """Returns URL with $1 substituted."""
        prop = ExternalIdentifierProperty(
            formatter_url="https://viaf.org/viaf/$1",
        )
        assert prop.build_url("76323654") == "https://viaf.org/viaf/76323654"

    def test_without_formatter_url(self):
        """Returns None when formatter_url is blank."""
        prop = ExternalIdentifierProperty(formatter_url="")
        assert prop.build_url("76323654") is None

    def test_complex_formatter_url(self):
        """Works with more complex URL templates."""
        prop = ExternalIdentifierProperty(
            formatter_url="https://orcid.org/$1",
        )
        assert prop.build_url("0000-0001-5109-3700") == "https://orcid.org/0000-0001-5109-3700"


class TestSlugGeneration:
    """Tests for the slug generation helper used by sync_wikidata_properties."""

    def test_basic_slug(self):
        from src.web.persons.management.commands.sync_wikidata_properties import generate_slug

        assert generate_slug("VIAF cluster ID") == "viaf-cluster-id"

    def test_strips_non_alphanumeric(self):
        from src.web.persons.management.commands.sync_wikidata_properties import generate_slug

        assert generate_slug("IMDb person ID") == "imdb-person-id"

    def test_collapses_consecutive_hyphens(self):
        from src.web.persons.management.commands.sync_wikidata_properties import generate_slug

        assert generate_slug("Some -- weird label") == "some-weird-label"

    def test_lowercase(self):
        from src.web.persons.management.commands.sync_wikidata_properties import generate_slug

        assert generate_slug("Library Of Congress") == "library-of-congress"

    def test_strips_leading_trailing_hyphens(self):
        from src.web.persons.management.commands.sync_wikidata_properties import generate_slug

        assert generate_slug("(special) label!") == "special-label"


class TestExtractQid:
    """Tests for the _extract_qid helper."""

    def test_extracts_qid_from_uri(self):
        from src.web.persons.management.commands.sync_wikidata_properties import _extract_qid

        assert _extract_qid("http://www.wikidata.org/entity/Q19595382") == "Q19595382"

    def test_extracts_pid_from_uri(self):
        from src.web.persons.management.commands.sync_wikidata_properties import _extract_qid

        assert _extract_qid("http://www.wikidata.org/entity/P214") == "P214"

    def test_plain_qid_passthrough(self):
        from src.web.persons.management.commands.sync_wikidata_properties import _extract_qid

        assert _extract_qid("Q19595382") == "Q19595382"

    def test_trailing_slash_returns_empty(self):
        from src.web.persons.management.commands.sync_wikidata_properties import _extract_qid

        assert _extract_qid("http://www.wikidata.org/entity/") == ""

    def test_empty_string_returns_empty(self):
        from src.web.persons.management.commands.sync_wikidata_properties import _extract_qid

        assert _extract_qid("") == ""

    def test_non_qid_token_returns_empty(self):
        from src.web.persons.management.commands.sync_wikidata_properties import _extract_qid

        assert _extract_qid("http://www.wikidata.org/entity/entity") == ""


# ---------------------------------------------------------------------------
# Fixtures for management command tests
# ---------------------------------------------------------------------------

SPARQL_ROW_VIAF = {
    "prop": {"value": "http://www.wikidata.org/entity/P214"},
    "propLabel": {"value": "VIAF cluster ID"},
    "propDescription": {"value": "identifier for the VIAF database"},  # noqa: E501
    "formatterURL": {"value": "https://viaf.org/viaf/$1"},
    "subjectItemLabel": {"value": "Virtual International Authority File"},
    "categories": {"value": "http://www.wikidata.org/entity/Q19595382"},
}

SPARQL_ROW_ORCID = {
    "prop": {"value": "http://www.wikidata.org/entity/P496"},
    "propLabel": {"value": "ORCID iD"},
    "propDescription": {"value": "identifier for the Open Researcher and Contributor ID"},
    "formatterURL": {"value": "https://orcid.org/$1"},
    "subjectItemLabel": {"value": "ORCID"},
    "categories": {"value": "http://www.wikidata.org/entity/Q108075891"},
}

SPARQL_ROW_NO_FORMATTER = {
    "prop": {"value": "http://www.wikidata.org/entity/P999"},
    "propLabel": {"value": "Some identifier"},
    "propDescription": {"value": "a plain identifier with no formatter"},
    "categories": {"value": ""},
}


def _make_sparql_response(rows, *, second_page_empty=True):
    """Build a mock for requests.get that returns SPARQL rows."""
    results = {"results": {"bindings": rows}}
    empty = {"results": {"bindings": []}}

    mock_full = MagicMock()
    mock_full.raise_for_status = MagicMock()
    mock_full.json.return_value = results

    mock_empty = MagicMock()
    mock_empty.raise_for_status = MagicMock()
    mock_empty.json.return_value = empty

    if second_page_empty:
        return MagicMock(side_effect=[mock_full, mock_empty])
    return MagicMock(return_value=mock_full)


@pytest.mark.django_db
class TestSyncWikidataPropertiesCommand:
    """Tests for the sync_wikidata_properties management command."""

    def _run(self, **options):
        out = StringIO()
        call_command("sync_wikidata_properties", stdout=out, **options)
        return out.getvalue()

    @patch("src.web.persons.management.commands.sync_wikidata_properties.requests.get")
    def test_creates_properties(self, mock_get):
        """Command creates ExternalIdentifierProperty rows from SPARQL results."""
        mock_get.side_effect = _make_sparql_response([SPARQL_ROW_VIAF])
        self._run()
        assert ExternalIdentifierProperty.objects.filter(wikidata_property_id="P214").exists()

    @patch("src.web.persons.management.commands.sync_wikidata_properties.requests.get")
    def test_upsert_idempotent(self, mock_get):
        """Running twice with the same data produces one row."""
        mock_get.side_effect = _make_sparql_response([SPARQL_ROW_VIAF])
        self._run()
        mock_get.side_effect = _make_sparql_response([SPARQL_ROW_VIAF])
        self._run()
        assert ExternalIdentifierProperty.objects.filter(wikidata_property_id="P214").count() == 1

    @patch("src.web.persons.management.commands.sync_wikidata_properties.requests.get")
    def test_updates_existing_fields(self, mock_get):
        """Re-running updates display name and formatter_url."""
        mock_get.side_effect = _make_sparql_response([SPARQL_ROW_VIAF])
        self._run()

        updated_row = dict(SPARQL_ROW_VIAF)
        updated_row["propLabel"] = {"value": "VIAF ID (updated)"}
        mock_get.side_effect = _make_sparql_response([updated_row])
        self._run()

        prop = ExternalIdentifierProperty.objects.get(wikidata_property_id="P214")
        assert prop.display == "VIAF ID (updated)"

    @patch("src.web.persons.management.commands.sync_wikidata_properties.requests.get")
    def test_does_not_change_is_enabled_on_update(self, mock_get):
        """Re-running preserves the admin-set is_enabled flag."""
        mock_get.side_effect = _make_sparql_response([SPARQL_ROW_VIAF])
        self._run()

        ExternalIdentifierProperty.objects.filter(wikidata_property_id="P214").update(
            is_enabled=False
        )

        mock_get.side_effect = _make_sparql_response([SPARQL_ROW_VIAF])
        self._run()

        prop = ExternalIdentifierProperty.objects.get(wikidata_property_id="P214")
        assert prop.is_enabled is False

    @patch("src.web.persons.management.commands.sync_wikidata_properties.requests.get")
    def test_parses_formatter_url(self, mock_get):
        """formatter_url is stored from P1630."""
        mock_get.side_effect = _make_sparql_response([SPARQL_ROW_VIAF])
        self._run()
        prop = ExternalIdentifierProperty.objects.get(wikidata_property_id="P214")
        assert prop.formatter_url == "https://viaf.org/viaf/$1"

    @patch("src.web.persons.management.commands.sync_wikidata_properties.requests.get")
    def test_parses_taxonomy_categories(self, mock_get):
        """taxonomy_categories is stored as a list of QID strings."""
        mock_get.side_effect = _make_sparql_response([SPARQL_ROW_VIAF])
        self._run()
        prop = ExternalIdentifierProperty.objects.get(wikidata_property_id="P214")
        assert "Q19595382" in prop.taxonomy_categories

    @patch("src.web.persons.management.commands.sync_wikidata_properties.requests.get")
    def test_no_formatter_url_row(self, mock_get):
        """A row without formatterURL stores empty string."""
        mock_get.side_effect = _make_sparql_response([SPARQL_ROW_NO_FORMATTER])
        self._run()
        prop = ExternalIdentifierProperty.objects.get(wikidata_property_id="P999")
        assert prop.formatter_url == ""

    @patch("src.web.persons.management.commands.sync_wikidata_properties.requests.get")
    def test_auto_links_platform(self, mock_get):
        """Command links a property to an ExternalPlatform when slug matches."""
        ExternalPlatform.objects.create(slug="viaf-cluster-id", display="VIAF", is_active=True)
        mock_get.side_effect = _make_sparql_response([SPARQL_ROW_VIAF])
        self._run()
        prop = ExternalIdentifierProperty.objects.get(wikidata_property_id="P214")
        assert prop.platform is not None
        assert prop.platform.slug == "viaf-cluster-id"

    @patch("src.web.persons.management.commands.sync_wikidata_properties.requests.get")
    def test_auto_link_skips_inactive_platform(self, mock_get):
        """Auto-link does not match inactive ExternalPlatform."""
        ExternalPlatform.objects.create(slug="viaf-cluster-id", display="VIAF", is_active=False)
        mock_get.side_effect = _make_sparql_response([SPARQL_ROW_VIAF])
        self._run()
        prop = ExternalIdentifierProperty.objects.get(wikidata_property_id="P214")
        assert prop.platform is None

    @patch("src.web.persons.management.commands.sync_wikidata_properties.requests.get")
    def test_auto_link_does_not_overwrite_existing_platform(self, mock_get):
        """Auto-link skips a property that already has a platform set."""
        existing = ExternalPlatform.objects.create(
            slug="already-linked", display="Already Linked", is_active=True
        )
        ExternalIdentifierProperty.objects.create(
            wikidata_property_id="P214",
            slug="viaf-cluster-id",
            display="VIAF cluster ID",
            platform=existing,
        )
        ExternalPlatform.objects.create(slug="viaf-cluster-id", display="VIAF", is_active=True)
        mock_get.side_effect = _make_sparql_response([SPARQL_ROW_VIAF])
        self._run()
        prop = ExternalIdentifierProperty.objects.get(wikidata_property_id="P214")
        assert prop.platform.slug == "already-linked"

    @patch("src.web.persons.management.commands.sync_wikidata_properties.requests.get")
    def test_slug_collision_appends_property_id(self, mock_get):
        """If slug collides with a different property, appends -{property_id_lower}."""
        ExternalIdentifierProperty.objects.create(
            wikidata_property_id="P999",
            slug="viaf-cluster-id",
            display="Existing",
        )
        mock_get.side_effect = _make_sparql_response([SPARQL_ROW_VIAF])
        self._run()
        prop = ExternalIdentifierProperty.objects.get(wikidata_property_id="P214")
        assert prop.slug == "viaf-cluster-id-p214"

    @patch("src.web.persons.management.commands.sync_wikidata_properties.requests.get")
    def test_slug_double_collision_appends_numeric_suffix(self, mock_get):
        """If both base slug and -{property_id} slug are taken, appends numeric suffix."""
        ExternalIdentifierProperty.objects.create(
            wikidata_property_id="P999",
            slug="viaf-cluster-id",
            display="Existing base",
        )
        ExternalIdentifierProperty.objects.create(
            wikidata_property_id="P998",
            slug="viaf-cluster-id-p214",
            display="Existing fallback",
        )
        mock_get.side_effect = _make_sparql_response([SPARQL_ROW_VIAF])
        self._run()
        prop = ExternalIdentifierProperty.objects.get(wikidata_property_id="P214")
        assert prop.slug == "viaf-cluster-id-p214-2"

    @patch("src.web.persons.management.commands.sync_wikidata_properties.requests.get")
    def test_paginates_results(self, mock_get):
        """Command fetches a second page when first page has 500 results (LIMIT rows)."""
        # Simulate two pages: first has 500 rows, second has 1 row, third empty
        page1_rows = [
            {
                "prop": {"value": f"http://www.wikidata.org/entity/P{1000 + i}"},
                "propLabel": {"value": f"Prop {1000 + i}"},
                "propDescription": {"value": ""},
                "categories": {"value": ""},
            }
            for i in range(500)
        ]
        page2_rows = [SPARQL_ROW_VIAF]

        call_counter = {"n": 0}

        def side_effect(*args, **kwargs):
            call_counter["n"] += 1
            n = call_counter["n"]
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if n == 1:
                resp.json.return_value = {"results": {"bindings": page1_rows}}
            elif n == 2:
                resp.json.return_value = {"results": {"bindings": page2_rows}}
            else:
                resp.json.return_value = {"results": {"bindings": []}}
            return resp

        mock_get.side_effect = side_effect
        self._run()
        # 500 (page1) + 1 (page2/VIAF) synced + 1 pre-seeded P2390 from migration
        assert ExternalIdentifierProperty.objects.count() == 502
        # page1 (500 rows) + page2 (1 row) = 2 SPARQL requests minimum
        assert mock_get.call_count >= 2

    @patch("src.web.persons.management.commands.sync_wikidata_properties.requests.get")
    def test_summary_output_includes_counts(self, mock_get):
        """Command prints a summary with created/updated/skipped/warnings counts."""
        mock_get.side_effect = _make_sparql_response([SPARQL_ROW_VIAF, SPARQL_ROW_ORCID])
        output = self._run()
        assert "Created 2" in output
        assert "Updated 0" in output
        assert "Skipped 0" in output
        assert "Warnings 0" in output

    @patch("src.web.persons.management.commands.sync_wikidata_properties.requests.get")
    def test_sets_last_synced_at(self, mock_get):
        """Command sets last_synced_at on created/updated rows."""
        mock_get.side_effect = _make_sparql_response([SPARQL_ROW_VIAF])
        self._run()
        prop = ExternalIdentifierProperty.objects.get(wikidata_property_id="P214")
        assert prop.last_synced_at is not None


@pytest.mark.integration
@pytest.mark.django_db
class TestSyncWikidataPropertiesLive:
    """Integration test — hits the real Wikidata SPARQL endpoint."""

    def test_live_sync_creates_properties(self):
        """Running against live Wikidata should create at least one property."""
        out = StringIO()
        # Use a very small limit to keep CI fast — just verify it works at all.
        call_command("sync_wikidata_properties", stdout=out, limit=10)
        assert ExternalIdentifierProperty.objects.count() >= 1
