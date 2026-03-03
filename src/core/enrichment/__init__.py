"""Enrichment provider framework.

Public re-exports for the enrichment package.
"""

from src.core.enrichment.base import (
    EnrichmentResult,
    EnrichmentRunResult,
    EnrichmentWarning,
    PersonData,
    Provider,
)
from src.core.enrichment.registry import ProviderRegistry
from src.core.enrichment.runner import EnrichmentRunner

__all__ = [
    "EnrichmentResult",
    "EnrichmentRunResult",
    "EnrichmentWarning",
    "PersonData",
    "Provider",
    "ProviderRegistry",
    "EnrichmentRunner",
]
