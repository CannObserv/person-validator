"""Keys app configuration."""

from django.apps import AppConfig


class KeysConfig(AppConfig):
    """Configuration for the API keys app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "src.web.keys"
    label = "keys"
    verbose_name = "API Keys"
