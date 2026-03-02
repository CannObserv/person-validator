"""Tests for src.core.matching — normalize and search."""

from src.core.matching import normalize


class TestNormalize:
    """Tests for the normalize function."""

    def test_lowercases(self):
        assert normalize("Robert Smith") == "robert smith"

    def test_strips_punctuation(self):
        assert normalize("Smith, Jr.") == "smith jr"

    def test_collapses_whitespace(self):
        assert normalize("  Bob   Smith  ") == "bob smith"

    def test_strips_underscores(self):
        assert normalize("bob_smith") == "bobsmith"

    def test_strips_digits(self):
        assert normalize("John Smith 3rd") == "john smith rd"

    def test_preserves_apostrophe_letters(self):
        """O'Brien becomes obrien (apostrophe stripped, letters kept)."""
        assert normalize("O'Brien") == "obrien"

    def test_empty_string(self):
        assert normalize("") == ""

    def test_whitespace_only(self):
        assert normalize("   ") == ""
