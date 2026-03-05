"""Utilities for working with person names in the enrichment pipeline."""

import re
import unicodedata

# Unicode block ranges covering non-Latin scripts of interest.
# Each tuple is (start, end) inclusive code-point range.
_NON_LATIN_RANGES: list[tuple[int, int]] = [
    (0x0400, 0x04FF),  # Cyrillic
    (0x0600, 0x06FF),  # Arabic
    (0x0900, 0x097F),  # Devanagari
    (0x0980, 0x09FF),  # Bengali
    (0x0A80, 0x0AFF),  # Gujarati
    (0x0B00, 0x0B7F),  # Oriya
    (0x0B80, 0x0BFF),  # Tamil
    (0x0C00, 0x0C7F),  # Telugu
    (0x0C80, 0x0CFF),  # Kannada
    (0x0D00, 0x0D7F),  # Malayalam
    (0x0E00, 0x0E7F),  # Thai
    (0x0E80, 0x0EFF),  # Lao
    (0x1000, 0x109F),  # Myanmar
    (0x10A0, 0x10FF),  # Georgian
    (0x1200, 0x137F),  # Ethiopic
    (0x3040, 0x309F),  # Hiragana
    (0x30A0, 0x30FF),  # Katakana
    (0x3400, 0x4DBF),  # CJK Extension A
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0xAC00, 0xD7AF),  # Hangul Syllables
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
    (0x20000, 0x2A6DF),  # CJK Extension B
]

_PERIOD_INITIALS_RE = re.compile(r"^(?:[A-Za-z]\.)+$")


def _has_non_latin_chars(text: str) -> bool:
    """Return True if *text* contains at least one non-Latin script character."""
    for char in text:
        cp = ord(char)
        for start, end in _NON_LATIN_RANGES:
            if start <= cp <= end:
                return True
    return False


def _is_latin_primary(primary_name: str | None) -> bool:
    """Return True when *primary_name* is None or contains no non-Latin chars."""
    if primary_name is None:
        return True
    return not _has_non_latin_chars(primary_name)


def infer_name_type(full_name: str, primary_name: str | None) -> str:
    """Infer the name_type for a provider-created PersonName record.

    Rules (applied in order; first match wins):

    1. If *full_name* contains only non-Latin characters **and** the person's
       primary name is Latin-script (or unknown) → ``"transliteration"``.
    2. If *full_name* is ≤6 characters and is all-caps, OR matches the
       period-separated-initials pattern (e.g. ``"J.F.K."``) → ``"abbreviation"``.
    3. Default → ``"alias"``.

    These heuristics are conservative. When in doubt the function returns
    ``"alias"`` rather than a more specific type.

    Args:
        full_name: The candidate name string (as it will be stored).
        primary_name: The person's current primary full_name, or ``None`` if
            not available.  Used only for the transliteration check.

    Returns:
        A string matching one of the ``NAME_TYPE_CHOICES`` values.
    """
    # Strip whitespace for length/case checks
    stripped = full_name.strip()

    # --- Rule 1: transliteration ---
    if _has_non_latin_chars(stripped) and _is_latin_primary(primary_name):
        # Confirm the name is *predominantly* non-Latin (ignore spaces/punctuation)
        letter_chars = [c for c in stripped if unicodedata.category(c).startswith("L")]
        if letter_chars and all(_has_non_latin_chars(c) for c in letter_chars):
            return "transliteration"

    # --- Rule 2: abbreviation ---
    no_space = stripped.replace(" ", "")
    if _PERIOD_INITIALS_RE.match(no_space):
        return "abbreviation"
    if (
        3 <= len(stripped) <= 6
        and stripped.upper() == stripped
        and stripped.replace(" ", "").isalpha()
        and not _has_non_latin_chars(stripped)
    ):
        return "abbreviation"

    # --- Default ---
    return "alias"
