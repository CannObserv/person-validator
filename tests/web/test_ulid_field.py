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

    def test_deconstruct_omits_defaults(self):
        """deconstruct should omit kwargs that match ULIDField defaults."""
        field = ULIDField()
        _name, _path, _args, kwargs = field.deconstruct()
        assert "max_length" not in kwargs
        assert "default" not in kwargs
        assert "editable" not in kwargs

    def test_deconstruct_preserves_primary_key(self):
        """deconstruct should keep primary_key when set."""
        field = ULIDField(primary_key=True)
        _name, _path, _args, kwargs = field.deconstruct()
        assert kwargs["primary_key"] is True

    def test_deconstruct_preserves_custom_max_length(self):
        """deconstruct should keep max_length if overridden."""
        field = ULIDField(max_length=30)
        _name, _path, _args, kwargs = field.deconstruct()
        assert kwargs["max_length"] == 30
