"""Name normalization pipeline framework.

Public API:
    PipelineResult  — dataclass produced by Pipeline.run()
    Stage           — abstract base for pipeline stages
    Pipeline        — ordered chain of Stage instances
    StageRegistry   — named registry for building pipelines from config
    BasicNormalization — first concrete stage (lowercase, whitespace, punctuation)
"""

from src.core.pipeline.base import Pipeline, PipelineResult, Stage
from src.core.pipeline.registry import StageRegistry
from src.core.pipeline.stages import BasicNormalization

__all__ = [
    "BasicNormalization",
    "Pipeline",
    "PipelineResult",
    "Stage",
    "StageRegistry",
]
