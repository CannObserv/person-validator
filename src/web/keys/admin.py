"""Admin configuration for APIKey model."""

from django.contrib import admin, messages

from src.web.keys.models import APIKey


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    """Admin interface for API key management."""

    list_display = ("key_prefix", "label", "user", "is_active", "created_at", "last_used_at")
    list_filter = ("is_active", "user")
    search_fields = ("label", "key_prefix")
    readonly_fields = ("id", "key_hash", "key_prefix", "created_at", "updated_at", "last_used_at")
    actions = ["generate_api_key"]

    def get_fieldsets(self, request, obj=None):
        """Customize fieldsets: hide hash/prefix when adding (they're auto-generated)."""
        if obj is None:
            # Adding a new key — only show user, label, and optional fields
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
