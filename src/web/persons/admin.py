"""Admin configuration for persons app models.

Covers Person, PersonName, PersonAttribute, AttributeLabel, and ExternalPlatform.
"""

from django.contrib import admin

from src.web.persons.models import (
    AttributeLabel,
    EnrichmentRun,
    ExternalPlatform,
    Person,
    PersonAttribute,
    PersonName,
)


class PersonNameInline(admin.TabularInline):
    """Inline editor for PersonName records on the Person admin page."""

    model = PersonName
    extra = 0
    fields = (
        "name_type",
        "full_name",
        "given_name",
        "middle_name",
        "surname",
        "prefix",
        "suffix",
        "is_primary",
        "source",
        "confidence",
        "provenance",
    )
    readonly_fields = ("created_at", "updated_at")


class PersonAttributeInline(admin.TabularInline):
    """Read-only inline for PersonAttribute records on the Person admin page."""

    model = PersonAttribute
    extra = 0
    fields = ("source", "key", "value", "value_type", "confidence", "created_at")
    readonly_fields = ("source", "key", "value", "value_type", "confidence", "created_at")


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    """Admin interface for Person with PersonName and PersonAttribute inlines."""

    list_display = ("name", "given_name", "surname", "created_at")
    search_fields = ("name", "given_name", "surname")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [PersonNameInline, PersonAttributeInline]


@admin.register(PersonName)
class PersonNameAdmin(admin.ModelAdmin):
    """Standalone admin for PersonName — useful for inspecting enrichment-created names.

    PersonName records are also accessible as an inline on PersonAdmin (for
    contextual display within a single person record). Both registrations are
    intentional and serve different purposes.
    """

    list_display = (
        "person",
        "full_name",
        "name_type",
        "confidence",
        "is_primary",
        "source",
        "created_at",
    )
    list_filter = ("name_type", "source", "is_primary")
    search_fields = ("person__name", "full_name", "source")
    readonly_fields = ("id", "created_at", "updated_at")
    fields = (
        "id",
        "person",
        "name_type",
        "full_name",
        "given_name",
        "middle_name",
        "surname",
        "prefix",
        "suffix",
        "is_primary",
        "source",
        "confidence",
        "provenance",
        "effective_date",
        "end_date",
        "notes",
        "created_at",
        "updated_at",
    )


@admin.register(PersonAttribute)
class PersonAttributeAdmin(admin.ModelAdmin):
    """Standalone admin for PersonAttribute with filtering by type and source.

    PersonAttribute is intentionally registered both here (for cross-person
    querying and filtering) and as a read-only inline on PersonAdmin (for
    contextual display within a single person record). The two registrations
    serve different purposes and are both intentional.
    """

    list_display = ("person", "source", "key", "value", "value_type", "confidence", "created_at")
    list_filter = ("source", "key", "value_type")
    search_fields = ("person__name", "source", "key", "value")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(AttributeLabel)
class AttributeLabelAdmin(admin.ModelAdmin):
    """Admin for the controlled label vocabulary."""

    list_display = ("value_type", "slug", "display", "sort_order", "is_active")
    list_filter = ("value_type", "is_active")
    search_fields = ("slug", "display")
    ordering = ("value_type", "sort_order", "slug")


@admin.register(ExternalPlatform)
class ExternalPlatformAdmin(admin.ModelAdmin):
    """Admin for the external platform/identity vocabulary."""

    list_display = ("slug", "display", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("slug", "display")
    ordering = ("sort_order", "slug")


@admin.register(EnrichmentRun)
class EnrichmentRunAdmin(admin.ModelAdmin):
    """Read-only admin for the EnrichmentRun audit log."""

    list_display = (
        "person",
        "provider",
        "status",
        "attributes_saved",
        "attributes_skipped",
        "triggered_by",
        "started_at",
        "completed_at",
    )
    list_filter = ("provider", "status", "triggered_by")
    search_fields = ("person__name", "provider")
    readonly_fields = (
        "id",
        "person",
        "provider",
        "status",
        "attributes_saved",
        "attributes_skipped",
        "warnings",
        "error",
        "triggered_by",
        "started_at",
        "completed_at",
    )

    def has_add_permission(self, request) -> bool:  # noqa: ANN001
        """Prevent manual creation of audit log entries."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # noqa: ANN001
        """Prevent editing of audit log entries."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ANN001
        """Prevent deletion of audit log entries."""
        return False
