"""Tests for NicknameExpansion pipeline stage."""

from src.core.pipeline.base import Pipeline, PipelineResult
from src.core.pipeline.nickname_expansion import NicknameExpansion

NICKNAME_WEIGHT = 0.85


def _run(name: str) -> PipelineResult:
    return Pipeline(stages=[NicknameExpansion()]).run(name)


class TestNicknameGeneration:
    def test_generates_formal_from_nickname(self):
        result = _run("denny heck")
        names = [v.name for v in result.variants]
        # "denny" → canonicals_of → includes "dennis"
        assert any("dennis" in n for n in names)

    def test_generates_nickname_from_formal(self):
        result = _run("dennis heck")
        names = [v.name for v in result.variants]
        # "dennis" → nicknames_of → includes "denny"
        assert any("denny" in n for n in names)

    def test_variant_weight_is_085(self):
        result = _run("denny heck")
        for v in result.variants:
            assert v.weight == NICKNAME_WEIGHT

    def test_no_variants_for_unknown_name(self):
        """A given name with no known nicknames should produce no variants."""
        result = _run("xyzabc smith")
        assert result.variants == []

    def test_single_token_input_no_crash(self):
        result = _run("alice")
        # Should not raise; may or may not produce variants
        assert isinstance(result.variants, list)

    def test_resolved_unchanged(self):
        result = _run("denny heck")
        assert result.resolved == "denny heck"

    def test_passes_through_messages(self):
        stage = NicknameExpansion()
        r = PipelineResult(original="Bob", resolved="bob smith", messages=["prior"])
        result = stage.process(r)
        assert "prior" in result.messages

    def test_passes_through_is_valid_name(self):
        stage = NicknameExpansion()
        r = PipelineResult(original="Bob", resolved="bob smith", is_valid_name=False)
        result = stage.process(r)
        assert result.is_valid_name is False
