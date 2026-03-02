"""API Key model for authenticating requests to the FastAPI service."""

import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from src.core.fields import ULIDField


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

    def __str__(self) -> str:
        return f"{self.key_prefix}… ({self.label})"

    @classmethod
    def generate(cls, *, user, label: str) -> tuple[str, "APIKey"]:
        """Generate a new API key.

        Returns a (raw_key, api_key_instance) tuple. The raw key is only
        available at creation time — it is not stored.
        """
        raw_key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:8]
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

        Returns the APIKey instance if valid, or None if the key is
        wrong, revoked, or expired. Updates last_used_at on success.
        """
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        now = timezone.now()
        try:
            api_key = cls.objects.get(
                key_hash=key_hash,
                is_active=True,
            )
        except cls.DoesNotExist:
            return None

        if api_key.expires_at is not None and api_key.expires_at <= now:
            return None

        cls.objects.filter(pk=api_key.pk).update(
            last_used_at=now,
            updated_at=now,
        )
        api_key.last_used_at = now
        return api_key
