"""Admin configuration for APIKey model."""

from datetime import timedelta

from django.contrib import admin, messages
from django.utils import timezone

from src.web.keys.models import APIKey


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    """Admin interface for API key management."""

    list_display = ("key_prefix", "label", "user", "is_active", "created_at", "last_used_at")
    list_filter = ("is_active", "user")
    search_fields = ("label", "key_prefix")
    readonly_fields = ("id", "key_hash", "key_prefix", "created_at", "updated_at", "last_used_at")
    actions = None

    def get_readonly_fields(self, request, obj=None):
        """Make expires_at and user read-only on the change form.

        Expiration and ownership are set at key creation time.
        Changing expiration requires key rotation; user reassignment
        is not allowed.
        """
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            readonly.extend(["expires_at", "user"])
        return tuple(readonly)

    def get_fieldsets(self, request, obj=None):
        """Customize fieldsets: hide hash/prefix when adding (they're auto-generated)."""
        if obj is None:
            return [
                (None, {"fields": ("user", "label", "is_active", "expires_at")}),
            ]
        return [
            (
                None,
                {
                    "fields": (
                        "id",
                        "key_prefix",
                        "key_hash",
                        "user",
                        "label",
                        "is_active",
                        "expires_at",
                        "created_at",
                        "updated_at",
                        "last_used_at",
                    )
                },
            ),
        ]

    def get_form(self, request, obj=None, **kwargs):
        """Set default expires_at to 90 days from now on the add form."""
        form = super().get_form(request, obj, **kwargs)
        if obj is None:
            now = timezone.now()
            form.base_fields["expires_at"].initial = now + timedelta(days=90)
        return form

    def save_model(self, request, obj, form, change):
        """On create, generate a key and display the raw value once."""
        if not change:
            raw_key, key_hash, key_prefix = APIKey.prepare_raw_key()
            obj.key_hash = key_hash
            obj.key_prefix = key_prefix
            obj.save()
            messages.warning(
                request,
                f"Your new API key: {raw_key} \u2014 copy it now, it will not be shown again.",
            )
        else:
            obj.save()
