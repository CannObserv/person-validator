"""Admin configuration for APIKey model."""

import hashlib
import secrets
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
    actions = ["generate_api_key"]

    def get_readonly_fields(self, request, obj=None):
        """Make expires_at read-only on the change form (require key rotation)."""
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            readonly.append("expires_at")
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
            raw_key = secrets.token_urlsafe(32)
            obj.key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
            obj.key_prefix = raw_key[:8]
            obj.save()
            messages.warning(
                request,
                f"Your new API key: {raw_key} — copy it now, it will not be shown again.",
            )
        else:
            obj.save()

    @admin.action(description="Generate a new API key for selected users' keys")
    def generate_api_key(self, request, queryset):
        """Generate new API keys — operates on selected keys' users.

        This is primarily meant as a convenience action. For each selected
        row, it generates a new key for that row's user.
        """
        for api_key in queryset:
            raw_key, new_key = APIKey.generate(
                user=api_key.user,
                label=f"Generated from {api_key.label}",
            )
            messages.success(
                request,
                f"New key for {api_key.user}: {raw_key} "
                f"(prefix: {new_key.key_prefix}). "
                f"Copy this now — it will not be shown again.",
            )
