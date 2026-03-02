"""Concrete pipeline stages."""

from __future__ import annotations

import re

from src.core.pipeline.base import PipelineResult, Stage

# Matches characters to remove: everything except ASCII letters, whitespace, hyphens.
# Explicitly uses [^a-zA-Z\s-] rather than [^\w\s-] so that underscores and
# digits are stripped, consistent with the normalize() function in matching.py.
_STRIP_RE = re.compile(r"[^a-zA-Z\s-]")
# Collapse runs of whitespace (including tabs/newlines)
_SPACE_RE = re.compile(r"\s+")


class BasicNormalization(Stage):
    """Minimal normalization stage.

    Transforms the resolved name by:
    - Lowercasing
    - Removing characters other than ASCII letters, whitespace, and hyphens
    - Collapsing whitespace and stripping leading/trailing space

    This stage only updates ``resolved``; it never appends to ``variants``.
    It is the caller's responsibility to include ``resolved`` in the variant
    list passed to the matching layer.
    """

    def process(self, result: PipelineResult) -> PipelineResult:
        """Return a new PipelineResult with the normalized resolved name."""
        normalized = result.resolved.lower()
        normalized = _STRIP_RE.sub("", normalized)
        normalized = _SPACE_RE.sub(" ", normalized).strip()

        return PipelineResult(
            original=result.original,
            resolved=normalized,
            variants=list(result.variants),
        )
