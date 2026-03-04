"""Enrichment provider framework.

Public re-exports for the enrichment package.
"""

from src.core.enrichment.attribute_types import (
    LABELABLE_TYPES,
    VALUE_TYPE_CHOICES,
    AttributeValue,
    DateAttributeValue,
    EmailAttributeValue,
    LocationAttributeValue,
    PhoneAttributeValue,
    PlatformUrlAttributeValue,
    TextAttributeValue,
    UrlAttributeValue,
)
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
    # Attribute types
    "AttributeValue",
    "DateAttributeValue",
    "EmailAttributeValue",
    "LABELABLE_TYPES",
    "LocationAttributeValue",
    "PhoneAttributeValue",
    "PlatformUrlAttributeValue",
    "TextAttributeValue",
    "UrlAttributeValue",
    "VALUE_TYPE_CHOICES",
    # Base abstractions
    "EnrichmentResult",
    "EnrichmentRunResult",
    "EnrichmentWarning",
    "PersonData",
    "Provider",
    # Registry & runner
    "ProviderRegistry",
    "EnrichmentRunner",
]
