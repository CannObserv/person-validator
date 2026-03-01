"""Tests for Person and PersonName admin configuration."""

import pytest
from django.contrib.admin.sites import AdminSite

from src.web.persons.admin import PersonAdmin, PersonNameInline
from src.web.persons.models import Person, PersonName


class TestPersonAdmin:
    """Tests for PersonAdmin configuration."""

    def test_list_display(self):
        """PersonAdmin list_display includes expected columns."""
        admin = PersonAdmin(Person, AdminSite())
        assert "name" in admin.list_display
        assert "given_name" in admin.list_display
        assert "surname" in admin.list_display
        assert "created_at" in admin.list_display

    def test_search_fields(self):
        """PersonAdmin search fields include name parts."""
        admin = PersonAdmin(Person, AdminSite())
        assert "name" in admin.search_fields
        assert "given_name" in admin.search_fields
        assert "surname" in admin.search_fields

    def test_has_person_name_inline(self):
        """PersonAdmin includes a PersonName inline."""
        admin = PersonAdmin(Person, AdminSite())
        inline_classes = [i.__class__ for i in admin.get_inline_instances(None)]
        assert PersonNameInline in inline_classes


class TestPersonNameInline:
    """Tests for PersonNameInline configuration."""

    def test_inline_model(self):
        """Inline is for PersonName model."""
        assert PersonNameInline.model is PersonName

    def test_inline_extra_is_zero(self):
        """Inline does not show empty extra rows by default."""
        assert PersonNameInline.extra == 0


@pytest.mark.django_db
class TestPersonAdminIntegration:
    """Integration tests for admin with real data."""

    def test_person_registered_in_admin(self):
        """Person model is registered in the admin site."""
        from django.contrib.admin import site

        assert Person in site._registry

    def test_person_name_not_registered_standalone(self):
        """PersonName should only be available as inline, not standalone."""
        from django.contrib.admin import site

        assert PersonName not in site._registry
