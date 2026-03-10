"""Core pipeline data structures: PipelineResult, WeightedVariant, Stage, Pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class WeightedVariant:
    """A name variant paired with a confidence weight.

    Attributes:
        name: The normalized name string to search against.
        weight: Multiplier applied to base certainty from the DB match.
                1.0 = full confidence; lower values reduce final certainty.
    """

    name: str
    weight: float


@dataclass
class PipelineResult:
    """The result produced by running a name through a Pipeline.

    Attributes:
        original: The raw input string, never modified.
        resolved: The best normalized form (primary candidate).
        variants: Weighted alternative strings to attempt matching on.
        messages: Soft warnings or informational notes about the input.
        is_valid_name: True/False when a stage is confident; None if not yet assessed.
    """

    original: str
    resolved: str
    variants: list[WeightedVariant] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    is_valid_name: bool | None = None


class Stage(ABC):
    """Abstract base class for a pipeline stage.

    Each stage receives the current PipelineResult and returns a
    (possibly modified) PipelineResult. Stages must not mutate the
    incoming result in-place; they should return a new instance.

    Stages must propagate all fields they do not modify:
    ``original``, ``messages``, and ``is_valid_name`` are pass-through
    unless the stage explicitly changes them.
    """

    @abstractmethod
    def process(self, result: PipelineResult) -> PipelineResult:
        """Process *result* and return a new PipelineResult."""
        ...


class Pipeline:
    """An ordered chain of Stage instances.

    Receives a raw name string, passes it through each stage in
    sequence, and produces a final PipelineResult.
    """

    def __init__(self, stages: list[Stage]) -> None:
        self.stages = stages

    def run(self, name: str) -> PipelineResult:
        """Run *name* through all stages and return the final PipelineResult."""
        result = PipelineResult(original=name, resolved=name)
        for stage in self.stages:
            result = stage.process(result)
        return result
