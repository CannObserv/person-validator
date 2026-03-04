"""Pydantic v2 discriminated union for typed enrichment attribute values.

Also exports the canonical VALUE_TYPE_CHOICES list (used by Django models)
and LABELABLE_TYPES set (used by the runner) so both are single-sourced here.
"""

import datetime
from typing import Annotated, Literal

from pydantic import AnyUrl, BaseModel, Field, field_validator

# Canonical list of value types — imported by Django models for choices.
VALUE_TYPE_CHOICES = [
    ("text", "Text"),
    ("email", "Email"),
    ("phone", "Phone"),
    ("url", "URL"),
    ("platform_url", "Platform URL"),
    ("location", "Location"),
    ("date", "Date"),
]

# Value types whose metadata may carry a "label" list.
# Must stay in sync with VALUE_TYPE_CHOICES and the models that define label fields.
LABELABLE_TYPES: frozenset[str] = frozenset({"email", "phone", "url", "platform_url", "location"})


class EmailAttributeValue(BaseModel):
    """Typed model for email attributes."""

    type: Literal["email"]
    value: str
    label: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("value")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        """Validate basic email format (local@domain.tld)."""
        if "@" not in v or v.count("@") != 1:
            raise ValueError(f"Invalid email address: {v!r}")
        local, domain = v.split("@")
        if not local or not domain or "." not in domain:
            raise ValueError(f"Invalid email address: {v!r}")
        return v


class PhoneAttributeValue(BaseModel):
    """Typed model for phone attributes. Value must be in E.164 format."""

    type: Literal["phone"]
    value: str = Field(pattern=r"^\+[1-9]\d{1,14}$")
    label: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class UrlAttributeValue(BaseModel):
    """Typed model for generic URL attributes."""

    type: Literal["url"]
    value: AnyUrl
    label: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class PlatformUrlAttributeValue(BaseModel):
    """Typed model for social/platform profile URL attributes."""

    type: Literal["platform_url"]
    value: AnyUrl
    platform: str | None = None
    label: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class LocationAttributeValue(BaseModel):
    """Typed model for location attributes.

    Metadata fields mirror StandardizeResponseV1 from the Address Validator
    service (address_line_1, address_line_2, city, region, postal_code,
    country, standardized, components). All fields are optional to
    accommodate providers that supply partial location data.
    """

    type: Literal["location"]
    value: str  # human-readable display string
    label: list[str] = Field(default_factory=list)
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str | None = None
    standardized: str | None = None
    components: dict | None = None  # ComponentSet blob: {spec, spec_version, values}
    confidence: float = Field(ge=0.0, le=1.0)


class TextAttributeValue(BaseModel):
    """Typed model for plain-text attributes."""

    type: Literal["text"]
    value: str
    confidence: float = Field(ge=0.0, le=1.0)


class DateAttributeValue(BaseModel):
    """Typed model for date attributes. Value must be a valid ISO 8601 calendar date."""

    type: Literal["date"]
    value: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("value")
    @classmethod
    def validate_calendar_date(cls, v: str) -> str:
        """Ensure the value is a valid calendar date, not just a formatted string."""
        try:
            datetime.date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Invalid calendar date: {v!r}")
        return v


AttributeValue = Annotated[
    EmailAttributeValue
    | PhoneAttributeValue
    | UrlAttributeValue
    | PlatformUrlAttributeValue
    | LocationAttributeValue
    | TextAttributeValue
    | DateAttributeValue,
    Field(discriminator="type"),
]
