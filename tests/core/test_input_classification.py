"""Tests for InputClassification pipeline stage."""

from src.core.pipeline.base import Pipeline, PipelineResult
from src.core.pipeline.input_classification import InputClassification


def _run(name: str) -> PipelineResult:
    return Pipeline(stages=[InputClassification()]).run(name)


class TestOrgSuffixRejection:
    def test_llc_rejected(self):
        result = _run("Acme LLC")
        assert result.is_valid_name is False

    def test_corporation_rejected(self):
        result = _run("Acme Corporation")
        assert result.is_valid_name is False

    def test_inc_rejected(self):
        result = _run("Widgets Inc")
        assert result.is_valid_name is False

    def test_foundation_rejected(self):
        result = _run("Smith Foundation")
        assert result.is_valid_name is False

    def test_case_insensitive_suffix(self):
        result = _run("Acme llc")
        assert result.is_valid_name is False

    def test_message_set_on_rejection(self):
        result = _run("Acme LLC")
        assert any("organization" in m.lower() for m in result.messages)

    def test_person_name_not_rejected(self):
        result = _run("Alice Smith")
        assert result.is_valid_name is not False


class TestParenthesisStripping:
    def test_strips_parenthesized_content(self):
        result = _run("John Smith (DUPLICATE)")
        assert "duplicate" not in result.resolved.lower()
        assert "john smith" in result.resolved.lower()

    def test_message_added_for_stripped_parens(self):
        result = _run("John Smith (DUPLICATE)")
        assert any("parenthesized" in m.lower() or "removed" in m.lower() for m in result.messages)

    def test_empty_after_stripping_sets_invalid(self):
        result = _run("(DUPLICATE)")
        assert result.is_valid_name is False


class TestDigitStripping:
    def test_strips_digits(self):
        result = _run("John Smith 2")
        assert "2" not in result.resolved
        assert "john smith" in result.resolved.lower()

    def test_message_added_for_digits(self):
        result = _run("John Smith 2")
        assert any("digit" in m.lower() for m in result.messages)

    def test_all_digits_sets_invalid(self):
        result = _run("12345")
        assert result.is_valid_name is False


class TestEmailDecoding:
    def test_firstname_lastname_email_decoded(self):
        result = _run("john.smith@example.com")
        assert "john" in result.resolved.lower()
        assert "smith" in result.resolved.lower()

    def test_message_added_for_email(self):
        result = _run("john.smith@example.com")
        assert any("email" in m.lower() for m in result.messages)

    def test_opaque_email_not_decoded(self):
        """jsmith123@example.com has no decodable firstname.lastname pattern."""
        result = _run("jsmith123@example.com")
        # Should not produce a clean name variant; either invalid or unchanged
        assert "jsmith123" not in result.resolved or result.is_valid_name is False

    def test_valid_name_unchanged(self):
        result = _run("Alice Smith")
        assert result.resolved == "Alice Smith"
        assert result.messages == []
        assert result.is_valid_name is None
