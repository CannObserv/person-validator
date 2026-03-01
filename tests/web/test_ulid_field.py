"""Tests for the custom ULIDField."""

from ulid import ULID

from src.core.fields import ULIDField


class TestULIDField:
    """Test ULIDField behavior."""

    def test_field_max_length_is_26(self):
        """ULID string representation is always 26 characters."""
        field = ULIDField()
        assert field.max_length == 26

    def test_field_has_default(self):
        """Field should auto-generate a ULID default."""
        field = ULIDField()
        assert field.has_default()

    def test_default_generates_valid_ulid(self):
        """The default value should be a valid 26-char ULID string."""
        field = ULIDField()
        value = field.get_default()
        assert isinstance(value, str)
        assert len(value) == 26
        # Should parse without error
        ULID.from_str(value)

    def test_successive_defaults_are_unique(self):
        """Each call to get_default should produce a unique value."""
        field = ULIDField()
        values = {field.get_default() for _ in range(100)}
        assert len(values) == 100

    def test_successive_defaults_are_sortable(self):
        """Defaults generated in sequence should sort chronologically."""
        field = ULIDField()
        values = [field.get_default() for _ in range(10)]
        assert values == sorted(values)

    def test_internal_type_is_char(self):
        """DB column type should be CharField."""
        field = ULIDField()
        assert field.get_internal_type() == "CharField"

    def test_primary_key_usage(self):
        """Field should work as a primary key."""
        field = ULIDField(primary_key=True)
        assert field.primary_key is True
        assert field.editable is False
