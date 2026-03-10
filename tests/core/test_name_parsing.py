"""Tests for NameParsing pipeline stage."""

from src.core.pipeline.base import Pipeline, PipelineResult
from src.core.pipeline.name_parsing import NameParsing
from src.core.pipeline.stages import BasicNormalization


def _run(name: str) -> PipelineResult:
    return Pipeline(stages=[NameParsing()]).run(name)


class TestSurnameFirstDetection:
    def test_surname_first_reordered(self):
        result = _run("Heck, Denny")
        assert result.resolved.lower() == "denny heck"

    def test_message_added_for_reorder(self):
        result = _run("Heck, Denny")
        assert any("surname-first" in m.lower() or "reorder" in m.lower() for m in result.messages)

    def test_normal_order_unchanged(self):
        result = _run("Denny Heck")
        assert result.resolved == "Denny Heck"
        assert result.messages == []

    def test_surname_first_works_after_basic_normalization(self):
        """Surname-first correction must work end-to-end, after BasicNormalization strips commas."""
        pipeline = Pipeline(stages=[BasicNormalization(), NameParsing()])
        result = pipeline.run("Heck, Denny")
        assert result.resolved == "denny heck"

    def test_suffix_comma_no_false_reorder(self):
        """'Denny Heck, Jr.' has a suffix comma — must NOT trigger a surname-first message."""
        result = _run("Denny Heck, Jr.")
        assert "denny" in result.resolved.lower()
        assert not any(
            "reorder" in m.lower() or "surname-first" in m.lower() for m in result.messages
        )

    def test_suffix_comma_no_false_reorder_after_normalization(self):
        """End-to-end: 'Denny Heck, Jr.' through BasicNormalization + NameParsing."""
        pipeline = Pipeline(stages=[BasicNormalization(), NameParsing()])
        result = pipeline.run("Denny Heck, Jr.")
        assert result.resolved == "denny heck"
        assert not any(
            "reorder" in m.lower() or "surname-first" in m.lower() for m in result.messages
        )


class TestPrefixStripping:
    def test_strips_mr(self):
        result = _run("Mr. John Smith")
        assert "mr" not in result.resolved.lower()
        assert "john smith" in result.resolved.lower()

    def test_strips_dr(self):
        result = _run("Dr. Alice Jones")
        assert "dr" not in result.resolved.lower()

    def test_strips_lieutenant_governor(self):
        result = _run("Lieutenant Governor Heck")
        assert "lieutenant" not in result.resolved.lower()
        assert "governor" not in result.resolved.lower()
        assert "heck" in result.resolved.lower()


class TestSuffixStripping:
    def test_strips_jr(self):
        result = _run("John Smith Jr.")
        assert "jr" not in result.resolved.lower()
        assert "john smith" in result.resolved.lower()

    def test_strips_iii(self):
        result = _run("John Smith III")
        assert "iii" not in result.resolved.lower()


class TestPassthrough:
    def test_passes_through_messages(self):
        stage = NameParsing()
        r = PipelineResult(original="Alice", resolved="Alice", messages=["prior"])
        result = stage.process(r)
        assert "prior" in result.messages

    def test_passes_through_is_valid_name(self):
        stage = NameParsing()
        r = PipelineResult(original="Alice", resolved="Alice", is_valid_name=False)
        result = stage.process(r)
        assert result.is_valid_name is False
