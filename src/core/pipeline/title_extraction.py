"""TitleExtraction pipeline stage — extract surname from occupational title strings."""

from __future__ import annotations

from src.core.pipeline.base import PipelineResult, Stage, WeightedVariant

# Ordered list of multi-word title prefixes (longer first to match greedily).
# All entries are lowercase; matched against the lowercased resolved name.
_TITLE_PREFIXES: list[tuple[str, ...]] = [
    ("lieutenant", "governor"),
    ("vice", "president"),
    ("attorney", "general"),
    ("secretary", "of", "state"),
    ("lieutenant",),
    ("governor",),
    ("senator",),
    ("representative",),
    ("congressman",),
    ("congresswoman",),
    ("delegate",),
    ("mayor",),
    ("president",),
    ("commissioner",),
    ("councilman",),
    ("councilwoman",),
    ("councilmember",),
    ("assemblyman",),
    ("assemblywoman",),
    ("assemblymember",),
    ("treasurer",),
    ("comptroller",),
]

_TITLE_WEIGHT = 0.70


class TitleExtraction(Stage):
    """Extract a surname variant from occupational title prefixes.

    Detects known title words at the start of the resolved name and
    appends the remaining token(s) as a ``WeightedVariant`` at weight
    ``0.70``. The resolved form is left unchanged.

    Only single trailing tokens are extracted (e.g. ``"senator smith"``
    → ``"smith"``). Multi-token remainders are not appended to avoid
    false positives.
    """

    def process(self, result: PipelineResult) -> PipelineResult:
        """Append a surname variant if the resolved name starts with a title."""
        tokens = result.resolved.lower().split()
        remainder = self._strip_title(tokens)

        variants = list(result.variants)
        if remainder is not None and len(remainder) == 1:
            variants.append(WeightedVariant(name=remainder[0], weight=_TITLE_WEIGHT))

        return PipelineResult(
            original=result.original,
            resolved=result.resolved,
            variants=variants,
            messages=list(result.messages),
            is_valid_name=result.is_valid_name,
        )

    def _strip_title(self, tokens: list[str]) -> list[str] | None:
        """Return the token list after stripping a leading title, or None if no title found."""
        for prefix in _TITLE_PREFIXES:
            n = len(prefix)
            if tokens[:n] == list(prefix) and len(tokens) > n:
                return tokens[n:]
        return None
