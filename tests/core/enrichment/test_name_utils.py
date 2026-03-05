"""Tests for infer_name_type utility (issue #16)."""

from src.core.enrichment.name_utils import infer_name_type


class TestInferNameType:
    """Tests for infer_name_type(full_name, primary_name) -> str."""

    def test_default_returns_alias(self):
        """A plain Latin-script name that doesn't match other rules returns 'alias'."""
        assert infer_name_type("John Smith", "George Washington") == "alias"

    def test_non_latin_arabic_returns_transliteration(self):
        """Arabic-script name returns 'transliteration' when primary is Latin."""
        arabic = "\u062c\u0648\u0631\u062c \u0648\u0627\u0634\u0646\u0637\u0646"
        assert infer_name_type(arabic, "George Washington") == "transliteration"

    def test_non_latin_cjk_returns_transliteration(self):
        """CJK-script name returns 'transliteration' when primary is Latin."""
        assert infer_name_type("\u534e\u76db\u987f", "George Washington") == "transliteration"

    def test_non_latin_cyrillic_returns_transliteration(self):
        """Cyrillic-script name returns 'transliteration' when primary is Latin."""
        # Дмитрий Менделеев
        given = "\u0414\u043c\u0438\u0442\u0440\u0438\u0439"
        family = "\u041c\u0435\u043d\u0434\u0435\u043b\u0435\u0435\u0432"
        assert infer_name_type(f"{given} {family}", "Dmitri Mendeleev") == "transliteration"

    def test_non_latin_devanagari_returns_transliteration(self):
        """Devanagari-script name returns 'transliteration' when primary is Latin."""
        devanagari = "\u092e\u0939\u093e\u0924\u094d\u092e\u093e \u0917\u093e\u0902\u0927\u0940"
        assert infer_name_type(devanagari, "Mahatma Gandhi") == "transliteration"

    def test_non_latin_when_primary_also_non_latin_returns_alias(self):
        """Non-Latin name returns 'alias' when primary is also non-Latin."""
        result = infer_name_type(
            "\u534e\u76db\u987f",
            "\u4e94\u6708\u82b1",
        )
        assert result == "alias"

    def test_short_allcaps_returns_abbreviation(self):
        """Short all-caps name (≤6 chars) returns 'abbreviation'."""
        assert infer_name_type("JFK", "John F. Kennedy") == "abbreviation"

    def test_period_separated_initials_returns_abbreviation(self):
        """Period-separated initials return 'abbreviation'."""
        assert infer_name_type("J.F.K.", "John F. Kennedy") == "abbreviation"

    def test_short_allcaps_exactly_six_chars(self):
        """6-char all-caps string still returns 'abbreviation'."""
        assert infer_name_type("ABCDEF", "Some Person") == "abbreviation"

    def test_long_allcaps_returns_alias(self):
        """7+ char all-caps string is not an abbreviation (returns 'alias')."""
        assert infer_name_type("ABCDEFG", "Some Person") == "alias"

    def test_alias_beats_nothing(self):
        """A mixed-case ordinary name returns 'alias'."""
        assert infer_name_type("The Artist", "Prince") == "alias"

    def test_primary_name_none_treated_as_latin(self):
        """When primary_name is None, non-Latin name returns 'transliteration'."""
        assert infer_name_type("\u062c\u0648\u0631\u062c", None) == "transliteration"

    # --- abbreviation minimum-length boundary (finding #2) ---

    def test_single_char_allcaps_returns_alias(self):
        """Single all-caps character is too short to be an abbreviation (< 3 chars)."""
        assert infer_name_type("A", "Alice") == "alias"

    def test_two_char_allcaps_returns_alias(self):
        """Two-char all-caps string is too short to be an abbreviation."""
        assert infer_name_type("ED", "Edward Jones") == "alias"

    def test_three_char_allcaps_returns_abbreviation(self):
        """3-char all-caps string is the minimum for abbreviation."""
        assert infer_name_type("JFK", "John F. Kennedy") == "abbreviation"

    # --- lowercase initials (finding #3) ---

    def test_lowercase_period_initials_returns_abbreviation(self):
        """Lowercase period-separated initials are treated as abbreviations."""
        assert infer_name_type("j.f.k.", "John F. Kennedy") == "abbreviation"

    def test_mixed_case_period_initials_returns_abbreviation(self):
        """Mixed-case period-separated initials are treated as abbreviations."""
        assert infer_name_type("J.f.K.", "John f. Kennedy") == "abbreviation"

    # --- empty / whitespace edge cases (finding #6) ---

    def test_empty_string_returns_alias(self):
        """Empty string returns 'alias' (no rules fire; conservative default)."""
        assert infer_name_type("", "George Washington") == "alias"

    def test_whitespace_only_returns_alias(self):
        """Whitespace-only string returns 'alias' after stripping."""
        assert infer_name_type("   ", "George Washington") == "alias"
