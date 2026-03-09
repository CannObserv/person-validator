"""App configuration for the persons app."""

from django.apps import AppConfig

from src.core.logging import get_logger

logger = get_logger(__name__)


class PersonsConfig(AppConfig):
    """Configuration for the persons Django app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "src.web.persons"
    verbose_name = "Persons"

    def ready(self) -> None:
        """Connect app signals and run startup checks."""
        from src.web.persons.signals import _connect_signals  # noqa: PLC0415

        _connect_signals()
        self._check_external_identifier_property_table()

    def _check_external_identifier_property_table(self) -> None:
        """Warn operators when ExternalIdentifierProperty table is empty.

        An empty table causes WikidataProvider to skip all external ID
        extraction silently.  This check surfaces the issue at startup so
        it appears in service logs on every restart until the operator
        runs ``manage.py sync_wikidata_properties``.
        """
        try:
            from src.web.persons.models import ExternalIdentifierProperty  # noqa: PLC0415

            if not ExternalIdentifierProperty.objects.filter(is_enabled=True).exists():
                logger.warning(
                    "ExternalIdentifierProperty table is empty. "
                    "WikidataProvider will skip external ID extraction until you run: "
                    "manage.py sync_wikidata_properties",
                )
        except Exception:  # noqa: BLE001
            # Table may not exist yet (pre-migration). Do not block startup.
            pass
