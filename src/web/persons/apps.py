"""App configuration for the persons app."""

from django.apps import AppConfig


class PersonsConfig(AppConfig):
    """Configuration for the persons Django app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "src.web.persons"
    verbose_name = "Persons"

    def ready(self) -> None:
        """Connect app signals."""
        from src.web.persons.signals import _connect_signals  # noqa: PLC0415

        _connect_signals()
