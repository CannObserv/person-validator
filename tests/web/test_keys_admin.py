"""Tests for APIKey admin configuration."""

from datetime import timedelta

import pytest
from django.contrib.admin import site as admin_site
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from django.utils import timezone

from src.web.keys.admin import APIKeyAdmin
from src.web.keys.models import APIKey

User = get_user_model()


@pytest.fixture
def staff_user(db):
    """Create a staff/superuser for admin requests."""
    return User.objects.create_user(
        username="admin",
        email="admin@example.com",
        is_staff=True,
        is_superuser=True,
    )


def _make_request(method, path, staff_user, data=None):
    """Build a request with session and messages middleware wired up."""
    factory = RequestFactory()
    if method == "GET":
        request = factory.get(path)
    else:
        request = factory.post(path, data=data or {})
    request.user = staff_user
    # Wire up messages framework
    setattr(request, "session", "session")
    messages = FallbackStorage(request)
    setattr(request, "_messages", messages)
    return request


class TestAPIKeyVerboseNames:
    """Tests that 'API' is always ALL CAPS in admin labels."""

    def test_verbose_name_is_api_key(self):
        """Model verbose_name should be 'API key' (ALL CAPS API)."""
        assert APIKey._meta.verbose_name == "API key"

    def test_verbose_name_plural_is_api_keys(self):
        """Model verbose_name_plural should be 'API keys' (ALL CAPS API)."""
        assert APIKey._meta.verbose_name_plural == "API keys"


class TestAPIKeyAdminConfig:
    """Tests for APIKeyAdmin configuration."""

    def test_registered_in_admin(self):
        """APIKey model is registered in the admin site."""
        assert APIKey in admin_site._registry

    def test_list_display(self):
        """list_display includes expected columns."""
        admin = APIKeyAdmin(APIKey, AdminSite())
        assert "key_prefix" in admin.list_display
        assert "label" in admin.list_display
        assert "user" in admin.list_display
        assert "is_active" in admin.list_display
        assert "created_at" in admin.list_display
        assert "last_used_at" in admin.list_display

    def test_list_filter(self):
        """list_filter includes is_active and user."""
        admin = APIKeyAdmin(APIKey, AdminSite())
        assert "is_active" in admin.list_filter
        assert "user" in admin.list_filter

    def test_search_fields(self):
        """search_fields includes label and key_prefix."""
        admin = APIKeyAdmin(APIKey, AdminSite())
        assert "label" in admin.search_fields
        assert "key_prefix" in admin.search_fields

    def test_readonly_fields(self):
        """key_hash, key_prefix, created_at, last_used_at are read-only."""
        admin = APIKeyAdmin(APIKey, AdminSite())
        assert "key_hash" in admin.readonly_fields
        assert "key_prefix" in admin.readonly_fields
        assert "created_at" in admin.readonly_fields
        assert "last_used_at" in admin.readonly_fields


@pytest.mark.django_db
class TestAPIKeyAdminAddForm:
    """Tests for the Add API Key admin interface."""

    def test_add_view_fields_exclude_hash_and_prefix(self, staff_user):
        """When adding a new key, key_hash and key_prefix should not be shown."""
        admin = APIKeyAdmin(APIKey, AdminSite())
        request = _make_request("GET", "/admin/keys/apikey/add/", staff_user)
        fieldsets = admin.get_fieldsets(request)
        all_fields = []
        for _, opts in fieldsets:
            all_fields.extend(opts["fields"])
        assert "key_hash" not in all_fields
        assert "key_prefix" not in all_fields

    def test_add_form_defaults_expires_at_to_90_days(self, staff_user):
        """The add form should pre-populate expires_at ~90 days from now."""
        admin = APIKeyAdmin(APIKey, AdminSite())
        request = _make_request("GET", "/admin/keys/apikey/add/", staff_user)
        form_class = admin.get_form(request, obj=None)
        form = form_class()
        initial = form["expires_at"].value()
        # Should be approximately 90 days from now (within a minute tolerance)
        expected = timezone.now() + timedelta(days=90)
        delta = abs(expected - initial)
        assert delta < timedelta(minutes=1)

    def test_save_model_generates_key_and_shows_raw_value(self, staff_user):
        """Saving a new APIKey via admin generates the key and shows it in messages."""
        admin = APIKeyAdmin(APIKey, AdminSite())
        request = _make_request("POST", "/admin/keys/apikey/add/", staff_user)
        # Create a minimal form-like object — save_model receives the unsaved obj
        form_class = admin.get_form(request, obj=None)
        expires = timezone.now() + timedelta(days=90)
        form = form_class(
            data={
                "user": staff_user.pk,
                "label": "Test Key",
                "is_active": True,
                "expires_at_0": expires.strftime("%Y-%m-%d"),
                "expires_at_1": expires.strftime("%H:%M:%S"),
            }
        )
        assert form.is_valid(), form.errors
        obj = form.save(commit=False)
        admin.save_model(request, obj, form, change=False)

        # The object should now be persisted with a generated key
        assert obj.pk is not None
        assert obj.key_hash != ""
        assert obj.key_prefix != ""

        # The raw key should appear in the success message
        stored_messages = list(request._messages)
        assert len(stored_messages) >= 1
        raw_key_msg = stored_messages[0].message
        # The message should contain the key prefix
        assert obj.key_prefix in raw_key_msg

    def test_save_model_raw_key_hashes_to_stored_hash(self, staff_user):
        """The raw key shown in the message should hash to the stored key_hash."""
        import hashlib

        admin = APIKeyAdmin(APIKey, AdminSite())
        request = _make_request("POST", "/admin/keys/apikey/add/", staff_user)
        form_class = admin.get_form(request, obj=None)
        expires = timezone.now() + timedelta(days=90)
        form = form_class(
            data={
                "user": staff_user.pk,
                "label": "Hash Check",
                "is_active": True,
                "expires_at_0": expires.strftime("%Y-%m-%d"),
                "expires_at_1": expires.strftime("%H:%M:%S"),
            }
        )
        assert form.is_valid(), form.errors
        obj = form.save(commit=False)
        admin.save_model(request, obj, form, change=False)

        # Extract the raw key from the message
        msg = list(request._messages)[0].message
        # The message format includes the raw key — extract it
        # We can verify by checking that hashing yields the stored hash
        # The raw key is between specific markers in the message
        assert obj.key_hash in [hashlib.sha256(word.encode()).hexdigest() for word in msg.split()]


@pytest.mark.django_db
class TestAPIKeyAdminChangeForm:
    """Tests for the Change API Key admin interface."""

    def test_expires_at_readonly_on_change(self, staff_user):
        """expires_at should be read-only when editing an existing key."""
        admin = APIKeyAdmin(APIKey, AdminSite())
        _, api_key = APIKey.generate(user=staff_user, label="Existing")
        request = _make_request(
            "GET",
            f"/admin/keys/apikey/{api_key.pk}/change/",
            staff_user,
        )
        readonly = admin.get_readonly_fields(request, obj=api_key)
        assert "expires_at" in readonly

    def test_expires_at_not_readonly_on_add(self, staff_user):
        """expires_at should be editable when adding a new key."""
        admin = APIKeyAdmin(APIKey, AdminSite())
        request = _make_request("GET", "/admin/keys/apikey/add/", staff_user)
        readonly = admin.get_readonly_fields(request, obj=None)
        assert "expires_at" not in readonly


@pytest.mark.django_db
class TestAPIKeyAdminCreateAction:
    """Tests for the custom create key admin action."""

    def test_generate_api_key_action_exists(self, staff_user):
        """The admin should have a generate_api_key action."""
        admin = APIKeyAdmin(APIKey, AdminSite())
        request = _make_request("GET", "/admin/keys/apikey/", staff_user)
        actions = admin.get_actions(request)
        assert "generate_api_key" in actions
