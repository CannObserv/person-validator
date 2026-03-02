"""Tests for APIKey admin configuration."""

import pytest
from django.contrib.admin import site as admin_site
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from src.web.keys.admin import APIKeyAdmin
from src.web.keys.models import APIKey

User = get_user_model()


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
class TestAPIKeyAdminCreateAction:
    """Tests for the custom create key admin action."""

    def test_generate_api_key_action_exists(self):
        """The admin should have a generate_api_key action."""
        admin = APIKeyAdmin(APIKey, AdminSite())
        factory = RequestFactory()
        request = factory.get("/admin/keys/apikey/")
        request.user = User(is_superuser=True, is_staff=True)
        actions = admin.get_actions(request)
        assert "generate_api_key" in actions

    def test_add_view_fields_exclude_hash_and_prefix(self):
        """When adding a new key, key_hash and key_prefix should not be shown."""
        admin = APIKeyAdmin(APIKey, AdminSite())
        factory = RequestFactory()
        request = factory.get("/admin/keys/apikey/add/")
        request.user = User(is_superuser=True, is_staff=True)
        fieldsets = admin.get_fieldsets(request)
        all_fields = []
        for _, opts in fieldsets:
            all_fields.extend(opts["fields"])
        # key_hash and key_prefix should not appear in add form
        assert "key_hash" not in all_fields
        assert "key_prefix" not in all_fields
