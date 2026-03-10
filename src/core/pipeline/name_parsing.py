"""NameParsing pipeline stage — parse name components using nameparser."""

from __future__ import annotations

from nameparser import HumanName

from src.core.pipeline.base import PipelineResult, Stage


class NameParsing(Stage):
    """Parse name structure using the ``nameparser`` library.

    - Detects and corrects surname-first ordering (``"Heck, Denny"``).
    - Strips honorific prefixes (``"Mr."``, ``"Dr."``, ``"Lieutenant Governor"``).
    - Strips generational suffixes (``"Jr."``, ``"III"``).

    Updates ``resolved`` with the cleaned, reordered name.
    Does not append to ``variants`` — the resolved form retains weight 1.0.
    """

    def process(self, result: PipelineResult) -> PipelineResult:
        """Parse and normalize the resolved name."""
        messages = list(result.messages)
        name = HumanName(result.resolved)

        # Detect surname-first: input contained a comma (e.g. "Heck, Denny")
        was_surname_first = "," in result.resolved

        # Reconstruct: first [middle] last — drop title/prefix and suffix
        parts = [p for p in [name.first, name.middle, name.last] if p]
        resolved = " ".join(parts) if parts else result.resolved

        original_sans_comma = result.resolved.replace(",", "").strip().lower()
        if was_surname_first and resolved.lower() != original_sans_comma:
            messages.append("Surname-first format detected and corrected")

        return PipelineResult(
            original=result.original,
            resolved=resolved,
            variants=list(result.variants),
            messages=messages,
            is_valid_name=result.is_valid_name,
        )
