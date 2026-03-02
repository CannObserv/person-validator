"""Core pipeline data structures: PipelineResult, Stage, Pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class PipelineResult:
    """The result produced by running a name through a Pipeline.

    Attributes:
        original: The raw input string, never modified.
        resolved: The best normalized form (primary candidate).
        variants: All variant strings to attempt matching on.
    """

    original: str
    resolved: str
    variants: list[str] = field(default_factory=list)


class Stage(ABC):
    """Abstract base class for a pipeline stage.

    Each stage receives the current PipelineResult and returns a
    (possibly modified) PipelineResult.  Stages must not mutate the
    incoming result in-place; they should return a new instance.
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
        result = PipelineResult(original=name, resolved=name, variants=[])
        for stage in self.stages:
            result = stage.process(result)
        return result
