"""Custom model fields for the Person Validator project."""

from django.db import models
from ulid import ULID


def _generate_ulid() -> str:
    """Generate a new ULID string."""
    return str(ULID())


class ULIDField(models.CharField):
    """CharField-backed field that auto-generates ULID values.

    ULIDs are 26-character, lexicographically sortable, universally unique
    identifiers. Suitable for use as primary keys.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 26)
        kwargs.setdefault("default", _generate_ulid)
        kwargs.setdefault("editable", False)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        """Remove kwargs that match ULIDField defaults so migrations stay clean."""
        name, path, args, kwargs = super().deconstruct()
        if kwargs.get("max_length") == 26:
            del kwargs["max_length"]
        if kwargs.get("default") is _generate_ulid:
            del kwargs["default"]
        if kwargs.get("editable") is False:
            del kwargs["editable"]
        return name, path, args, kwargs

    def get_internal_type(self) -> str:
        """Return the database column type."""
        return "CharField"
