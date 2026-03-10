"""NicknameExpansion pipeline stage — generate given-name variants via nickname lookup."""

from __future__ import annotations

from nicknames import NickNamer

from src.core.pipeline.base import PipelineResult, Stage, WeightedVariant

_NAMER = NickNamer()
_NICKNAME_WEIGHT = 0.85


class NicknameExpansion(Stage):
    """Generate given-name alternatives using a nickname lookup database.

    Splits the resolved name into tokens, treats the first token as the
    given name, and looks up nickname and canonical-name variants in both
    directions. Each variant replaces the first token and is appended to
    ``variants`` with weight ``0.85``.

    Requires the resolved name to have at least two tokens (given + surname).
    Single-token inputs are passed through without modification.
    """

    def process(self, result: PipelineResult) -> PipelineResult:
        """Append nickname variants for the given name."""
        parts = result.resolved.split()
        if len(parts) < 2:
            return PipelineResult(
                original=result.original,
                resolved=result.resolved,
                variants=list(result.variants),
                messages=list(result.messages),
                is_valid_name=result.is_valid_name,
            )

        given = parts[0]
        rest = parts[1:]

        # Collect related names in both directions (nickname ↔ canonical).
        related: set[str] = set()
        related.update(n.lower() for n in _NAMER.nicknames_of(given))
        related.update(n.lower() for n in _NAMER.canonicals_of(given))
        related.discard(given.lower())

        new_variants = [
            WeightedVariant(
                name=" ".join([alt, *rest]),
                weight=_NICKNAME_WEIGHT,
            )
            for alt in sorted(related)
        ]

        return PipelineResult(
            original=result.original,
            resolved=result.resolved,
            variants=[*result.variants, *new_variants],
            messages=list(result.messages),
            is_valid_name=result.is_valid_name,
        )
