"""Tests for APIKey model and key lifecycle."""

import hashlib
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from src.core.fields import ULIDField
from src.web.keys.models import APIKey

User = get_user_model()


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(username="testuser", email="test@example.com")


@pytest.mark.django_db
class TestAPIKeyModel:
    """Tests for the APIKey model fields and basic creation."""

    def test_pk_is_ulid_field(self):
        """APIKey.id should be a ULIDField primary key."""
        field = APIKey._meta.get_field("id")
        assert isinstance(field, ULIDField)
        assert field.primary_key is True

    def test_create_api_key(self, user):
        """An APIKey can be created with required fields."""
        key_hash = hashlib.sha256(b"test-raw-key").hexdigest()
        api_key = APIKey.objects.create(
            key_hash=key_hash,
            key_prefix="test-raw",
            user=user,
            label="Test Key",
        )
        assert api_key.pk is not None
        assert len(api_key.pk) == 26

    def test_key_hash_is_indexed(self):
        """key_hash field should be indexed for lookup performance."""
        field = APIKey._meta.get_field("key_hash")
        assert field.db_index is True

    def test_is_active_default_true(self, user):
        """is_active defaults to True."""
        key_hash = hashlib.sha256(b"active-key").hexdigest()
        api_key = APIKey.objects.create(
            key_hash=key_hash,
            key_prefix="active-k",
            user=user,
            label="Active",
        )
        assert api_key.is_active is True

    def test_expires_at_nullable(self, user):
        """expires_at is nullable (key never expires by default)."""
        key_hash = hashlib.sha256(b"no-expire").hexdigest()
        api_key = APIKey.objects.create(
            key_hash=key_hash,
            key_prefix="no-expir",
            user=user,
            label="No Expiry",
        )
        assert api_key.expires_at is None

    def test_last_used_at_nullable(self, user):
        """last_used_at is nullable (never used yet)."""
        key_hash = hashlib.sha256(b"unused-key").hexdigest()
        api_key = APIKey.objects.create(
            key_hash=key_hash,
            key_prefix="unused-k",
            user=user,
            label="Unused",
        )
        assert api_key.last_used_at is None

    def test_timestamps(self, user):
        """created_at and updated_at are set automatically."""
        key_hash = hashlib.sha256(b"ts-key").hexdigest()
        api_key = APIKey.objects.create(
            key_hash=key_hash,
            key_prefix="ts-key00",
            user=user,
            label="Timestamps",
        )
        assert api_key.created_at is not None
        assert api_key.updated_at is not None

    def test_timestamps_are_utc(self, user):
        """Timestamps must be timezone-aware and in UTC."""
        key_hash = hashlib.sha256(b"utc-key").hexdigest()
        api_key = APIKey.objects.create(
            key_hash=key_hash,
            key_prefix="utc-key0",
            user=user,
            label="UTC",
        )
        api_key.refresh_from_db()
        assert api_key.created_at.utcoffset() == timedelta(0)
        assert api_key.updated_at.utcoffset() == timedelta(0)

    def test_str_representation(self, user):
        """String representation shows prefix and label."""
        key_hash = hashlib.sha256(b"str-key").hexdigest()
        api_key = APIKey.objects.create(
            key_hash=key_hash,
            key_prefix="str-key0",
            user=user,
            label="My Label",
        )
        result = str(api_key)
        assert "str-key0" in result
        assert "My Label" in result

    def test_cascade_delete_user(self, user):
        """Deleting a User cascades to their APIKeys."""
        key_hash = hashlib.sha256(b"cascade").hexdigest()
        APIKey.objects.create(
            key_hash=key_hash,
            key_prefix="cascade0",
            user=user,
            label="Cascade",
        )
        user_id = user.pk
        user.delete()
        assert APIKey.objects.filter(user_id=user_id).count() == 0

    def test_db_table_name(self):
        """The model uses a custom table name."""
        assert APIKey._meta.db_table == "keys_apikey"


@pytest.mark.django_db
class TestAPIKeyGeneration:
    """Tests for key generation class method."""

    def test_generate_returns_raw_key_and_instance(self, user):
        """generate() returns (raw_key, api_key_instance)."""
        raw_key, api_key = APIKey.generate(user=user, label="Generated")
        assert isinstance(raw_key, str)
        assert isinstance(api_key, APIKey)
        assert api_key.pk is not None

    def test_generated_raw_key_is_high_entropy(self, user):
        """Raw key should be sufficiently long (at least 32 chars)."""
        raw_key, _ = APIKey.generate(user=user, label="Entropy")
        assert len(raw_key) >= 32

    def test_generated_hash_matches_raw_key(self, user):
        """The stored hash should match SHA-256 of the raw key."""
        raw_key, api_key = APIKey.generate(user=user, label="Hash Check")
        expected_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        assert api_key.key_hash == expected_hash

    def test_generated_prefix_matches_raw_key(self, user):
        """key_prefix should be the first 8 chars of the raw key."""
        raw_key, api_key = APIKey.generate(user=user, label="Prefix")
        assert api_key.key_prefix == raw_key[:8]

    def test_generated_key_is_active(self, user):
        """Generated keys are active by default."""
        _, api_key = APIKey.generate(user=user, label="Active")
        assert api_key.is_active is True

    def test_generated_keys_are_unique(self, user):
        """Two generated keys should have different raw values."""
        raw1, _ = APIKey.generate(user=user, label="Key 1")
        raw2, _ = APIKey.generate(user=user, label="Key 2")
        assert raw1 != raw2


@pytest.mark.django_db
class TestAPIKeyValidation:
    """Tests for key validation class method."""

    def test_valid_key_returns_api_key(self, user):
        """validate() returns the APIKey for a correct raw key."""
        raw_key, api_key = APIKey.generate(user=user, label="Valid")
        result = APIKey.validate(raw_key)
        assert result is not None
        assert result.pk == api_key.pk

    def test_wrong_key_returns_none(self, user):
        """validate() returns None for a wrong key."""
        APIKey.generate(user=user, label="Wrong")
        result = APIKey.validate("totally-wrong-key")
        assert result is None

    def test_revoked_key_returns_none(self, user):
        """validate() returns None for a revoked (is_active=False) key."""
        raw_key, api_key = APIKey.generate(user=user, label="Revoked")
        api_key.is_active = False
        api_key.save()
        result = APIKey.validate(raw_key)
        assert result is None

    def test_expired_key_returns_none(self, user):
        """validate() returns None for an expired key."""
        raw_key, api_key = APIKey.generate(user=user, label="Expired")
        api_key.expires_at = timezone.now() - timedelta(hours=1)
        api_key.save()
        result = APIKey.validate(raw_key)
        assert result is None

    def test_future_expiry_is_valid(self, user):
        """validate() returns the key if expires_at is in the future."""
        raw_key, api_key = APIKey.generate(user=user, label="Future")
        api_key.expires_at = timezone.now() + timedelta(days=30)
        api_key.save()
        result = APIKey.validate(raw_key)
        assert result is not None
        assert result.pk == api_key.pk

    def test_validate_updates_last_used_at(self, user):
        """validate() updates last_used_at on success."""
        raw_key, api_key = APIKey.generate(user=user, label="LastUsed")
        assert api_key.last_used_at is None
        before = timezone.now()
        result = APIKey.validate(raw_key)
        result.refresh_from_db()
        assert result.last_used_at is not None
        assert result.last_used_at >= before

    def test_validate_does_not_update_last_used_on_failure(self, user):
        """validate() does not touch last_used_at on failure."""
        _, api_key = APIKey.generate(user=user, label="NoTouch")
        APIKey.validate("bad-key")
        api_key.refresh_from_db()
        assert api_key.last_used_at is None


class TestPrepareRawKey:
    """Tests for the prepare_raw_key static method."""

    def test_returns_three_element_tuple(self):
        """prepare_raw_key() returns (raw_key, key_hash, key_prefix)."""
        result = APIKey.prepare_raw_key()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_raw_key_is_high_entropy(self):
        """Raw key should be at least 32 characters."""
        raw_key, _, _ = APIKey.prepare_raw_key()
        assert len(raw_key) >= 32

    def test_hash_matches_raw_key(self):
        """key_hash should be SHA-256 of raw_key."""
        raw_key, key_hash, _ = APIKey.prepare_raw_key()
        expected = hashlib.sha256(raw_key.encode()).hexdigest()
        assert key_hash == expected

    def test_prefix_matches_raw_key(self):
        """key_prefix should be first 8 chars of raw_key."""
        raw_key, _, key_prefix = APIKey.prepare_raw_key()
        assert key_prefix == raw_key[:8]

    def test_successive_calls_are_unique(self):
        """Two calls produce different raw keys."""
        raw1, _, _ = APIKey.prepare_raw_key()
        raw2, _, _ = APIKey.prepare_raw_key()
        assert raw1 != raw2
