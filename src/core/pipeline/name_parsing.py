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

        # BasicNormalization runs before this stage and strips commas from
        # result.resolved, so a comma in result.original is the only reliable
        # signal for surname-first format (e.g. "Heck, Denny").  When present,
        # parse from result.original so nameparser can see the comma marker.
        has_comma = "," in result.original
        source = result.original if has_comma else result.resolved
        name = HumanName(source)

        # Reconstruct: first [middle] last — drop title/prefix and suffix.
        parts = [p for p in [name.first, name.middle, name.last] if p]
        if has_comma:
            # Parsed from result.original (original casing), but BasicNormalization
            # has already run on resolved, so lowercase to stay consistent.
            parts = [p.lower() for p in parts]
        resolved = " ".join(parts) if parts else result.resolved

        # Report reordering only when the first token of the original actually
        # differs from the parsed given name — distinguishes true surname-first
        # ("Heck, Denny": first token "Heck" ≠ parsed first "Denny") from a
        # generational suffix comma ("Denny Heck, Jr.": first token "Denny" ==
        # parsed first "Denny").
        if has_comma:
            original_first = result.original.split()[0].lower().rstrip(",")
            if name.first.lower() != original_first:
                messages.append("Surname-first format detected and corrected")

        return PipelineResult(
            original=result.original,
            resolved=resolved,
            variants=list(result.variants),
            messages=messages,
            is_valid_name=result.is_valid_name,
        )
