"""Tests for src.core.pipeline.

Covers: PipelineResult, WeightedVariant, Stage, Pipeline, StageRegistry, BasicNormalization.
"""

import pytest

from src.core.pipeline import (
    BasicNormalization,
    Pipeline,
    PipelineResult,
    Stage,
    StageRegistry,
    WeightedVariant,
)


class TestWeightedVariant:
    """Tests for WeightedVariant dataclass."""

    def test_construction(self):
        v = WeightedVariant(name="bob smith", weight=0.85)
        assert v.name == "bob smith"
        assert v.weight == 0.85

    def test_immutable(self):
        v = WeightedVariant(name="bob smith", weight=0.85)
        with pytest.raises((AttributeError, TypeError)):
            v.name = "other"  # type: ignore[misc]


class TestPipelineResult:
    """Tests for PipelineResult dataclass."""

    def test_construction_minimal(self):
        r = PipelineResult(original="Bob Smith", resolved="bob smith")
        assert r.original == "Bob Smith"
        assert r.resolved == "bob smith"
        assert r.variants == []
        assert r.messages == []
        assert r.is_valid_name is None

    def test_construction_full(self):
        v = WeightedVariant(name="robert smith", weight=0.9)
        r = PipelineResult(
            original="Bob Smith",
            resolved="bob smith",
            variants=[v],
            messages=["Prefix stripped: Mr."],
            is_valid_name=True,
        )
        assert r.variants == [v]
        assert r.messages == ["Prefix stripped: Mr."]
        assert r.is_valid_name is True

    def test_variants_default_independent(self):
        r1 = PipelineResult(original="A", resolved="a")
        r2 = PipelineResult(original="B", resolved="b")
        r1.variants.append(WeightedVariant(name="a", weight=1.0))
        assert r2.variants == []

    def test_messages_default_independent(self):
        r1 = PipelineResult(original="A", resolved="a")
        r2 = PipelineResult(original="B", resolved="b")
        r1.messages.append("warning")
        assert r2.messages == []


class TestPipelineZeroStages:
    """Pipeline with no stages returns original input unchanged."""

    def test_empty_pipeline_returns_original(self):
        pipeline = Pipeline(stages=[])
        result = pipeline.run("Alice Jones")
        assert result.original == "Alice Jones"
        assert result.resolved == "Alice Jones"
        assert result.variants == []
        assert result.messages == []
        assert result.is_valid_name is None


class DummyUpperStage(Stage):
    """Test stage that uppercases resolved."""

    def process(self, result: PipelineResult) -> PipelineResult:
        return PipelineResult(
            original=result.original,
            resolved=result.resolved.upper(),
            variants=list(result.variants),
            messages=list(result.messages),
            is_valid_name=result.is_valid_name,
        )


class DummyAppendStage(Stage):
    """Test stage that appends a fixed WeightedVariant."""

    def __init__(self, variant_name: str, weight: float = 1.0) -> None:
        self.variant_name = variant_name
        self.weight = weight

    def process(self, result: PipelineResult) -> PipelineResult:
        return PipelineResult(
            original=result.original,
            resolved=result.resolved,
            variants=[
                *result.variants,
                WeightedVariant(name=self.variant_name, weight=self.weight),
            ],
            messages=list(result.messages),
            is_valid_name=result.is_valid_name,
        )


class TestPipelineOrdering:
    """Earlier stages feed into later stages."""

    def test_stages_run_in_order(self):
        pipeline = Pipeline(stages=[DummyAppendStage("first"), DummyAppendStage("second")])
        result = pipeline.run("x")
        assert [v.name for v in result.variants] == ["first", "second"]

    def test_later_stage_sees_earlier_resolved(self):
        pipeline = Pipeline(stages=[DummyUpperStage(), DummyAppendStage("appended")])
        result = pipeline.run("hello")
        assert result.resolved == "HELLO"
        assert any(v.name == "appended" for v in result.variants)


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
        registry.register("append", DummyAppendStage, config={"variant_name": "v"})
        pipeline = registry.build_pipeline(["upper", "append"])
        result = pipeline.run("hello")
        assert result.resolved == "HELLO"
        assert any(v.name == "v" for v in result.variants)

    def test_unknown_stage_raises(self):
        registry = StageRegistry()
        with pytest.raises(KeyError, match="unknown"):
            registry.build_stage("unknown")

    def test_register_overwrites(self):
        registry = StageRegistry()
        registry.register("s", DummyUpperStage)
        registry.register("s", DummyAppendStage, config={"variant_name": "x"})
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

    def test_does_not_append_variants(self):
        result = self._run("Robert Smith")
        assert result.variants == []

    def test_passes_through_messages(self):
        """BasicNormalization preserves messages set by earlier stages."""
        stage = BasicNormalization()
        r = PipelineResult(
            original="Bob",
            resolved="Bob",
            messages=["prior message"],
        )
        result = stage.process(r)
        assert result.messages == ["prior message"]

    def test_passes_through_is_valid_name(self):
        stage = BasicNormalization()
        r = PipelineResult(original="Bob", resolved="Bob", is_valid_name=False)
        result = stage.process(r)
        assert result.is_valid_name is False

    def test_strips_underscores(self):
        result = self._run("bob_smith")
        assert result.resolved == "bobsmith"

    def test_original_preserved(self):
        result = self._run("Robert Smith")
        assert result.original == "Robert Smith"

    def test_empty_string(self):
        result = self._run("")
        assert result.resolved == ""
        assert result.variants == []
