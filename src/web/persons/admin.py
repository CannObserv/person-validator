"""Admin configuration for Person, PersonName, and PersonAttribute models."""

from django.contrib import admin

from src.web.persons.models import Person, PersonAttribute, PersonName


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
    )
    readonly_fields = ("created_at", "updated_at")


class PersonAttributeInline(admin.TabularInline):
    """Read-only inline for PersonAttribute records on the Person admin page."""

    model = PersonAttribute
    extra = 0
    fields = ("source", "key", "value", "confidence", "created_at")
    readonly_fields = ("source", "key", "value", "confidence", "created_at")


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    """Admin interface for Person with PersonName and PersonAttribute inlines."""

    list_display = ("name", "given_name", "surname", "created_at")
    search_fields = ("name", "given_name", "surname")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [PersonNameInline, PersonAttributeInline]
