"""Accounts app configuration."""

from django.apps import AppConfig

from src.core.logging import configure_logging


class AccountsConfig(AppConfig):
    """Configuration for the accounts app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "src.web.accounts"
    label = "accounts"
    verbose_name = "Accounts"

    def ready(self) -> None:
        """Install JSON logging for the Django process."""
        configure_logging()
