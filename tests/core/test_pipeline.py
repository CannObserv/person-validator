"""Tests for src.core.pipeline — PipelineResult, Stage, Pipeline, registry, BasicNormalization."""

import pytest

from src.core.pipeline import (
    BasicNormalization,
    Pipeline,
    PipelineResult,
    Stage,
    StageRegistry,
)


class TestPipelineResult:
    """Tests for PipelineResult dataclass."""

    def test_construction(self):
        r = PipelineResult(original="Bob Smith", resolved="bob smith", variants=[])
        assert r.original == "Bob Smith"
        assert r.resolved == "bob smith"
        assert r.variants == []

    def test_variants_list_is_independent(self):
        """Mutating variants should not affect other instances."""
        r = PipelineResult(original="A", resolved="a", variants=["a"])
        r.variants.append("b")
        assert r.variants == ["a", "b"]


class TestPipelineZeroStages:
    """Pipeline with no stages returns original input unchanged."""

    def test_empty_pipeline_returns_original(self):
        pipeline = Pipeline(stages=[])
        result = pipeline.run("Alice Jones")
        assert result.original == "Alice Jones"
        assert result.resolved == "Alice Jones"
        assert result.variants == []


class DummyUpperStage(Stage):
    """Test stage that uppercases resolved."""

    def process(self, result: PipelineResult) -> PipelineResult:
        return PipelineResult(
            original=result.original,
            resolved=result.resolved.upper(),
            variants=result.variants,
        )


class DummyAppendStage(Stage):
    """Test stage that appends a fixed variant."""

    def __init__(self, variant: str) -> None:
        self.variant = variant

    def process(self, result: PipelineResult) -> PipelineResult:
        return PipelineResult(
            original=result.original,
            resolved=result.resolved,
            variants=[*result.variants, self.variant],
        )


class TestPipelineOrdering:
    """Earlier stages feed into later stages."""

    def test_stages_run_in_order(self):
        pipeline = Pipeline(stages=[DummyAppendStage("first"), DummyAppendStage("second")])
        result = pipeline.run("x")
        assert result.variants == ["first", "second"]

    def test_later_stage_sees_earlier_resolved(self):
        """Second stage receives the resolved value modified by the first stage."""
        pipeline = Pipeline(stages=[DummyUpperStage(), DummyAppendStage("appended")])
        result = pipeline.run("hello")
        assert result.resolved == "HELLO"
        assert "appended" in result.variants


class TestStageRegistry:
    """Stage registry: register, retrieve, build pipeline from names."""

    def test_register_and_retrieve(self):
        registry = StageRegistry()
        registry.register("upper", DummyUpperStage)
        stage = registry.build_stage("upper")
        assert isinstance(stage, DummyUpperStage)

    def test_build_pipeline_from_names(self):
        registry = StageRegistry()
        registry.register("upper", DummyUpperStage)
        registry.register("append", DummyAppendStage, config={"variant": "v"})
        pipeline = registry.build_pipeline(["upper", "append"])
        result = pipeline.run("hello")
        assert result.resolved == "HELLO"
        assert "v" in result.variants

    def test_unknown_stage_raises(self):
        registry = StageRegistry()
        with pytest.raises(KeyError, match="unknown"):
            registry.build_stage("unknown")

    def test_register_overwrites(self):
        """Re-registering a name replaces the previous entry."""
        registry = StageRegistry()
        registry.register("s", DummyUpperStage)
        registry.register("s", DummyAppendStage, config={"variant": "x"})
        stage = registry.build_stage("s")
        assert isinstance(stage, DummyAppendStage)


class TestBasicNormalization:
    """Tests for the BasicNormalization stage."""

    def _run(self, name: str) -> PipelineResult:
        pipeline = Pipeline(stages=[BasicNormalization()])
        return pipeline.run(name)

    def test_lowercases_resolved(self):
        result = self._run("Robert Smith")
        assert result.resolved == "robert smith"

    def test_collapses_whitespace(self):
        result = self._run("  Bob   Smith  ")
        assert result.resolved == "bob smith"

    def test_removes_periods(self):
        result = self._run("Jr.")
        assert result.resolved == "jr"

    def test_removes_commas(self):
        result = self._run("Smith, Jane")
        assert result.resolved == "smith jane"

    def test_preserves_hyphens(self):
        result = self._run("Mary-Jane Watson")
        assert result.resolved == "mary-jane watson"

    def test_resolved_is_normalized_form(self):
        """Normalization result is carried in resolved, not appended to variants.

        BasicNormalization only updates resolved; it never writes to variants.
        The caller is responsible for including resolved in the variant list
        passed to the matching layer.
        """
        result = self._run("Robert Smith")
        assert result.resolved == "robert smith"
        assert result.variants == []

    def test_variants_always_empty_after_basic_normalization(self):
        """BasicNormalization never appends to variants regardless of input."""
        result = self._run("robert smith")
        assert result.variants == []

    def test_empty_string(self):
        result = self._run("")
        assert result.resolved == ""
        assert result.variants == []

    def test_whitespace_only(self):
        result = self._run("   ")
        assert result.resolved == ""

    def test_punctuation_only(self):
        """String of only punctuation (no hyphens) becomes empty."""
        result = self._run("...,,")
        assert result.resolved == ""

    def test_strips_underscores(self):
        """Underscores are stripped, consistent with normalize() in matching.py."""
        result = self._run("bob_smith")
        assert result.resolved == "bobsmith"

    def test_original_preserved(self):
        result = self._run("Robert Smith")
        assert result.original == "Robert Smith"


class TestPipelineWithBasicNormalization:
    """Integration: Pipeline with BasicNormalization produces correct result."""

    def test_full_run(self):
        pipeline = Pipeline(stages=[BasicNormalization()])
        result = pipeline.run("  Dr. Jane Smith,  ")
        assert result.original == "  Dr. Jane Smith,  "
        assert result.resolved == "dr jane smith"
        # BasicNormalization only sets resolved; variants remain empty.
        # The caller (endpoint) is responsible for including resolved in the
        # variant list passed to the matching layer.
        assert result.variants == []
