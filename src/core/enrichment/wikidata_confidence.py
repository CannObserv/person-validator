"""Wikidata confidence constants shared between WikidataProvider and enrichment tasks.

Centralised here so that tasks.py (core layer) does not need to import the
WikidataProvider class (providers layer), and so that the constants have a
single authoritative home.
"""

# Confidence written to PersonAttribute / PersonName on unconfirmed auto-link.
AUTO_LINK_CONFIDENCE: float = 0.75

# Confidence written once a human admin confirms (or accepts) the link.
CONFIRMED_CONFIDENCE: float = 0.95

# Confidence written to PersonName alias rows on unconfirmed auto-link.
ALIAS_CONFIDENCE: float = 0.70

# Confidence written to PersonName alias rows after confirmation.
CONFIRMED_ALIAS_CONFIDENCE: float = 0.80

# Minimum score for a single candidate to be auto-linked without human review.
AUTO_LINK_THRESHOLD: float = 0.85
