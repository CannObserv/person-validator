"""InputClassification pipeline stage — clean and validate name input."""

from __future__ import annotations

import re

from src.core.pipeline.base import PipelineResult, Stage

# Known organization suffixes (matched at end of string, case-insensitive).
_ORG_SUFFIXES = frozenset(
    {
        "llc",
        "llp",
        "lp",
        "inc",
        "corp",
        "corporation",
        "ltd",
        "limited",
        "foundation",
        "association",
        "committee",
        "pac",
        "institute",
        "university",
        "college",
        "school",
        "company",
        "co",
        "trust",
        "agency",
        "bureau",
        "department",
        "office",
        "council",
        "authority",
        "district",
    }
)

# Matches one or more parenthesized groups anywhere in the string.
_PARENS_RE = re.compile(r"\([^)]*\)")
# Matches digit sequences.
_DIGITS_RE = re.compile(r"\d+")
# Matches firstname.lastname@domain pattern (two dot-separated alpha words before @).
_EMAIL_NAME_RE = re.compile(r"^([a-zA-Z]{2,})\.([a-zA-Z]{2,})@")


def _last_word(s: str) -> str:
    """Return the last whitespace-separated word of *s*, lowercased."""
    parts = s.strip().split()
    return parts[-1].lower() if parts else ""


class InputClassification(Stage):
    """Clean and classify name input before normalization.

    Operates on ``result.original`` to detect patterns that
    ``BasicNormalization`` would obscure (emails, parenthesized content).

    Clean-first strategy:
    - Decode ``firstname.lastname@domain`` email patterns.
    - Hard-reject on known org suffixes.
    - Strip parenthesized content and digits, adding soft messages.
    - Hard-reject after cleaning if the result is empty.

    Updates ``resolved`` with the cleaned form. Downstream stages
    (starting with ``BasicNormalization``) work from the cleaned string.
    """

    def process(self, result: PipelineResult) -> PipelineResult:
        """Return cleaned PipelineResult, setting is_valid_name when confident."""
        text = result.original
        messages = list(result.messages)

        # --- Email decoding (before org-suffix check to handle email input) ---
        email_match = _EMAIL_NAME_RE.match(text.strip())
        if email_match:
            first, last = email_match.group(1), email_match.group(2)
            text = f"{first.capitalize()} {last.capitalize()}"
            messages.append("Name extracted from email address")

        # --- Org suffix hard reject ---
        if _last_word(text) in _ORG_SUFFIXES:
            messages.append("Input rejected: appears to be an organization name")
            return PipelineResult(
                original=result.original,
                resolved=result.original,
                variants=list(result.variants),
                messages=messages,
                is_valid_name=False,
            )

        # --- Strip parenthesized content ---
        stripped, n_parens = _PARENS_RE.subn("", text)
        if n_parens:
            messages.append("Parenthesized content removed")
            text = stripped.strip()

        # --- Strip digits ---
        stripped, n_digits = _DIGITS_RE.subn("", text)
        if n_digits:
            messages.append("Digits removed from input")
            text = stripped.strip()

        # --- Post-cleaning validity check ---
        cleaned = text.strip()
        if not cleaned:
            messages.append("Input is empty after cleaning")
            return PipelineResult(
                original=result.original,
                resolved=result.original,
                variants=list(result.variants),
                messages=messages,
                is_valid_name=False,
            )

        return PipelineResult(
            original=result.original,
            resolved=cleaned,
            variants=list(result.variants),
            messages=messages,
            is_valid_name=result.is_valid_name,
        )
