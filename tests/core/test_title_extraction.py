"""Tests for TitleExtraction pipeline stage."""

from src.core.pipeline.base import Pipeline, PipelineResult
from src.core.pipeline.title_extraction import TitleExtraction

TITLE_WEIGHT = 0.70


def _run(name: str) -> PipelineResult:
    return Pipeline(stages=[TitleExtraction()]).run(name)


class TestTitleDetection:
    def test_senator_prefix_extracts_surname(self):
        result = _run("senator smith")
        names = [v.name for v in result.variants]
        assert "smith" in names

    def test_lieutenant_governor_extracts_surname(self):
        result = _run("lieutenant governor heck")
        names = [v.name for v in result.variants]
        assert "heck" in names

    def test_representative_prefix_extracts_surname(self):
        result = _run("representative jones")
        names = [v.name for v in result.variants]
        assert "jones" in names

    def test_title_variant_has_correct_weight(self):
        result = _run("senator smith")
        for v in result.variants:
            assert v.weight == TITLE_WEIGHT

    def test_no_title_produces_no_variants(self):
        result = _run("alice smith")
        assert result.variants == []

    def test_resolved_unchanged(self):
        result = _run("senator smith")
        assert result.resolved == "senator smith"

    def test_passes_through_messages(self):
        stage = TitleExtraction()
        r = PipelineResult(original="Senator Smith", resolved="senator smith", messages=["prior"])
        result = stage.process(r)
        assert "prior" in result.messages

    def test_passes_through_is_valid_name(self):
        stage = TitleExtraction()
        r = PipelineResult(original="Senator Smith", resolved="senator smith", is_valid_name=False)
        result = stage.process(r)
        assert result.is_valid_name is False
