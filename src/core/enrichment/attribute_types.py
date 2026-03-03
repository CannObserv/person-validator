"""Pydantic v2 discriminated union for typed enrichment attribute values."""

from typing import Annotated, Literal

from pydantic import AnyUrl, BaseModel, Field


class EmailAttributeValue(BaseModel):
    """Typed model for email attributes."""

    type: Literal["email"]
    value: str  # validated as email format via regex
    label: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)

    @classmethod
    def validate_email_format(cls, v: str) -> str:
        """Validate basic email format."""
        if "@" not in v or v.count("@") != 1:
            raise ValueError(f"Invalid email address: {v!r}")
        local, domain = v.split("@")
        if not local or not domain or "." not in domain:
            raise ValueError(f"Invalid email address: {v!r}")
        return v

    def model_post_init(self, __context) -> None:  # noqa: ANN001
        """Run post-init email validation."""
        self.validate_email_format(self.value)


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
    """Typed model for date attributes. Value must be ISO 8601 YYYY-MM-DD."""

    type: Literal["date"]
    value: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    confidence: float = Field(ge=0.0, le=1.0)


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
