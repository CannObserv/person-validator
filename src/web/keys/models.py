"""API Key model for authenticating requests to the FastAPI service."""

import hashlib
import secrets

from django.conf import settings
from django.db import connection as django_connection
from django.db import models

from src.core.fields import ULIDField
from src.core.key_validation import validate_api_key


class APIKey(models.Model):
    """An API key for authenticating external API requests.

    Raw keys are never stored. Only the SHA-256 hash is persisted.
    The first 8 characters of the raw key are stored as key_prefix
    for identification in admin lists.
    """

    id = ULIDField(primary_key=True)
    key_hash = models.CharField(max_length=64, db_index=True)
    key_prefix = models.CharField(max_length=8)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    label = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "keys_apikey"
        ordering = ["-created_at"]
        verbose_name = "API Key"
        verbose_name_plural = "API Keys"

    def __str__(self) -> str:
        return f"{self.key_prefix}… ({self.label})"

    @staticmethod
    def prepare_raw_key() -> tuple[str, str, str]:
        """Generate a raw key, its SHA-256 hash, and the 8-char prefix.

        Returns (raw_key, key_hash, key_prefix). The raw key is a
        high-entropy random string suitable for use as an API secret.
        """
        raw_key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        return raw_key, key_hash, raw_key[:8]

    @classmethod
    def generate(cls, *, user, label: str) -> tuple[str, "APIKey"]:
        """Generate a new API key.

        Returns a (raw_key, api_key_instance) tuple. The raw key is only
        available at creation time — it is not stored.
        """
        raw_key, key_hash, key_prefix = cls.prepare_raw_key()
        api_key = cls.objects.create(
            key_hash=key_hash,
            key_prefix=key_prefix,
            user=user,
            label=label,
        )
        return raw_key, api_key

    @classmethod
    def validate(cls, raw_key: str) -> "APIKey | None":
        """Validate a raw API key.

        Delegates to the shared ``core.key_validation`` module for the
        actual check, then returns the ORM instance on success.
        Returns None if the key is wrong, revoked, or expired.
        """
        django_connection.ensure_connection()
        result = validate_api_key(raw_key, django_connection.connection, commit=False)

        if not result.is_valid:
            return None

        try:
            return cls.objects.get(pk=result.key_id)
        except cls.DoesNotExist:
            return None
