"""Tests for the AttributeValue Pydantic discriminated union."""

import pytest
from pydantic import TypeAdapter, ValidationError

from src.core.enrichment.attribute_types import (
    AttributeValue,
    DateAttributeValue,
    EmailAttributeValue,
    LocationAttributeValue,
    PhoneAttributeValue,
    PlatformUrlAttributeValue,
    TextAttributeValue,
    UrlAttributeValue,
)

_adapter = TypeAdapter(AttributeValue)


class TestEmailAttributeValue:
    """Tests for EmailAttributeValue."""

    def test_valid_email(self):
        m = _adapter.validate_python(
            {"type": "email", "value": "alice@example.com", "confidence": 0.9}
        )
        assert isinstance(m, EmailAttributeValue)
        assert m.value == "alice@example.com"

    def test_label_defaults_empty(self):
        m = _adapter.validate_python({"type": "email", "value": "a@b.com", "confidence": 1.0})
        assert m.label == []

    def test_label_accepted(self):
        m = _adapter.validate_python(
            {"type": "email", "value": "a@b.com", "confidence": 1.0, "label": ["work"]}
        )
        assert m.label == ["work"]

    def test_multiple_labels(self):
        m = _adapter.validate_python(
            {"type": "email", "value": "a@b.com", "confidence": 1.0, "label": ["work", "personal"]}
        )
        assert m.label == ["work", "personal"]

    def test_invalid_email_no_at(self):
        with pytest.raises(ValidationError):
            _adapter.validate_python({"type": "email", "value": "notanemail", "confidence": 0.9})

    def test_invalid_email_no_domain(self):
        with pytest.raises(ValidationError):
            _adapter.validate_python({"type": "email", "value": "user@", "confidence": 0.9})

    def test_confidence_above_one_rejected(self):
        with pytest.raises(ValidationError):
            _adapter.validate_python({"type": "email", "value": "a@b.com", "confidence": 1.1})

    def test_confidence_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            _adapter.validate_python({"type": "email", "value": "a@b.com", "confidence": -0.1})


class TestPhoneAttributeValue:
    """Tests for PhoneAttributeValue."""

    def test_valid_e164(self):
        m = _adapter.validate_python({"type": "phone", "value": "+12125551234", "confidence": 0.8})
        assert isinstance(m, PhoneAttributeValue)
        assert m.value == "+12125551234"

    def test_label_accepted(self):
        m = _adapter.validate_python(
            {"type": "phone", "value": "+12125551234", "confidence": 0.8, "label": ["mobile"]}
        )
        assert m.label == ["mobile"]

    def test_invalid_no_plus(self):
        with pytest.raises(ValidationError):
            _adapter.validate_python({"type": "phone", "value": "12125551234", "confidence": 0.8})

    def test_invalid_too_short(self):
        with pytest.raises(ValidationError):
            _adapter.validate_python({"type": "phone", "value": "+1", "confidence": 0.8})

    def test_invalid_letters(self):
        with pytest.raises(ValidationError):
            _adapter.validate_python({"type": "phone", "value": "+1abc5551234", "confidence": 0.8})


class TestUrlAttributeValue:
    """Tests for UrlAttributeValue."""

    def test_valid_url(self):
        m = _adapter.validate_python(
            {"type": "url", "value": "https://example.com", "confidence": 0.7}
        )
        assert isinstance(m, UrlAttributeValue)

    def test_label_accepted(self):
        m = _adapter.validate_python(
            {"type": "url", "value": "https://example.com", "confidence": 0.7, "label": ["website"]}
        )
        assert m.label == ["website"]

    def test_invalid_url(self):
        with pytest.raises(ValidationError):
            _adapter.validate_python({"type": "url", "value": "not-a-url", "confidence": 0.7})


class TestPlatformUrlAttributeValue:
    """Tests for PlatformUrlAttributeValue."""

    def test_valid_with_platform(self):
        m = _adapter.validate_python(
            {
                "type": "platform_url",
                "value": "https://linkedin.com/in/alice",
                "platform": "linkedin",
                "confidence": 0.9,
            }
        )
        assert isinstance(m, PlatformUrlAttributeValue)
        assert m.platform == "linkedin"

    def test_platform_defaults_none(self):
        m = _adapter.validate_python(
            {"type": "platform_url", "value": "https://example.com", "confidence": 0.9}
        )
        assert m.platform is None

    def test_label_accepted(self):
        m = _adapter.validate_python(
            {
                "type": "platform_url",
                "value": "https://linkedin.com/in/alice",
                "platform": "linkedin",
                "label": ["work"],
                "confidence": 0.9,
            }
        )
        assert m.label == ["work"]

    def test_invalid_url(self):
        with pytest.raises(ValidationError):
            _adapter.validate_python(
                {"type": "platform_url", "value": "not-a-url", "confidence": 0.9}
            )


class TestLocationAttributeValue:
    """Tests for LocationAttributeValue."""

    def test_minimal_value(self):
        m = _adapter.validate_python(
            {"type": "location", "value": "Denver, CO, US", "confidence": 0.6}
        )
        assert isinstance(m, LocationAttributeValue)
        assert m.city is None

    def test_full_standardize_v1_shape(self):
        m = _adapter.validate_python(
            {
                "type": "location",
                "value": "123 MAIN ST, DENVER CO 80202",
                "address_line_1": "123 Main St",
                "address_line_2": "",
                "city": "Denver",
                "region": "CO",
                "postal_code": "80202",
                "country": "US",
                "standardized": "123 MAIN ST, DENVER CO 80202",
                "components": {
                    "spec": "usps-pub28",
                    "spec_version": "2024-07",
                    "values": {"StreetName": "MAIN"},
                },
                "label": ["home"],
                "confidence": 0.95,
            }
        )
        assert m.city == "Denver"
        assert m.region == "CO"
        assert m.postal_code == "80202"
        assert m.country == "US"
        assert m.components == {
            "spec": "usps-pub28",
            "spec_version": "2024-07",
            "values": {"StreetName": "MAIN"},
        }
        assert m.label == ["home"]

    def test_label_accepted(self):
        m = _adapter.validate_python(
            {"type": "location", "value": "NYC", "label": ["work", "current"], "confidence": 0.8}
        )
        assert m.label == ["work", "current"]


class TestTextAttributeValue:
    """Tests for TextAttributeValue."""

    def test_valid_text(self):
        m = _adapter.validate_python({"type": "text", "value": "Acme Corp", "confidence": 1.0})
        assert isinstance(m, TextAttributeValue)
        assert m.value == "Acme Corp"

    def test_no_label_field(self):
        m = _adapter.validate_python({"type": "text", "value": "foo", "confidence": 1.0})
        assert not hasattr(m, "label")


class TestDateAttributeValue:
    """Tests for DateAttributeValue."""

    def test_valid_date(self):
        m = _adapter.validate_python({"type": "date", "value": "1990-06-15", "confidence": 0.95})
        assert isinstance(m, DateAttributeValue)

    def test_invalid_format(self):
        with pytest.raises(ValidationError):
            _adapter.validate_python({"type": "date", "value": "June 15 1990", "confidence": 0.95})

    def test_invalid_partial_date(self):
        with pytest.raises(ValidationError):
            _adapter.validate_python({"type": "date", "value": "1990-06", "confidence": 0.95})


class TestDiscriminatedUnion:
    """Tests for the discriminated union dispatch."""

    @pytest.mark.parametrize(
        "value_type,payload",
        [
            (EmailAttributeValue, {"type": "email", "value": "x@y.com", "confidence": 1.0}),
            (PhoneAttributeValue, {"type": "phone", "value": "+441234567890", "confidence": 1.0}),
            (UrlAttributeValue, {"type": "url", "value": "https://x.com", "confidence": 1.0}),
            (
                PlatformUrlAttributeValue,
                {"type": "platform_url", "value": "https://x.com", "confidence": 1.0},
            ),  # noqa: E501
            (LocationAttributeValue, {"type": "location", "value": "Paris", "confidence": 1.0}),
            (TextAttributeValue, {"type": "text", "value": "hello", "confidence": 1.0}),
            (DateAttributeValue, {"type": "date", "value": "2000-01-01", "confidence": 1.0}),
        ],
    )
    def test_dispatch(self, value_type, payload):
        m = _adapter.validate_python(payload)
        assert isinstance(m, value_type)

    def test_unknown_type_rejected(self):
        with pytest.raises(ValidationError):
            _adapter.validate_python({"type": "unknown", "value": "x", "confidence": 1.0})
