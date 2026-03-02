"""Concrete pipeline stages."""

from __future__ import annotations

import re

from src.core.pipeline.base import PipelineResult, Stage

# Matches punctuation to remove: everything except letters, whitespace, hyphens
_STRIP_RE = re.compile(r"[^\w\s-]")
# Collapse runs of whitespace (including tabs/newlines)
_SPACE_RE = re.compile(r"\s+")


class BasicNormalization(Stage):
    """Minimal normalization stage.

    Transforms the resolved name by:
    - Lowercasing
    - Removing punctuation other than hyphens
    - Collapsing whitespace and stripping leading/trailing space

    If the normalized form differs from the incoming resolved value,
    it is appended to variants so the matching layer can search on it.
    """

    def process(self, result: PipelineResult) -> PipelineResult:
        """Return a new PipelineResult with the normalized resolved name."""
        normalized = result.resolved.lower()
        normalized = _STRIP_RE.sub("", normalized)
        normalized = _SPACE_RE.sub(" ", normalized).strip()

        variants = list(result.variants)
        if normalized != result.resolved and normalized not in variants:
            variants.append(normalized)

        return PipelineResult(
            original=result.original,
            resolved=normalized,
            variants=variants,
        )
