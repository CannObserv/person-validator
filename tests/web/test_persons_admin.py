"""Tests for Person, PersonName, PersonAttribute, AttributeLabel, and ExternalPlatform admin."""

import pytest
from django.contrib.admin import site as admin_site
from django.contrib.admin.sites import AdminSite

from src.web.persons.admin import (
    AttributeLabelAdmin,
    ExternalPlatformAdmin,
    PersonAdmin,
    PersonAttributeAdmin,
    PersonAttributeInline,
    PersonNameInline,
)
from src.web.persons.models import (
    AttributeLabel,
    ExternalPlatform,
    Person,
    PersonAttribute,
    PersonName,
)


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

    def test_has_person_attribute_inline(self):
        """PersonAdmin includes a PersonAttribute inline."""
        admin = PersonAdmin(Person, AdminSite())
        inline_classes = [i.__class__ for i in admin.get_inline_instances(None)]
        assert PersonAttributeInline in inline_classes


class TestPersonNameInline:
    """Tests for PersonNameInline configuration."""

    def test_inline_model(self):
        """Inline is for PersonName model."""
        assert PersonNameInline.model is PersonName

    def test_inline_extra_is_zero(self):
        """Inline does not show empty extra rows by default."""
        assert PersonNameInline.extra == 0


class TestPersonAttributeInline:
    """Tests for PersonAttributeInline configuration."""

    def test_inline_model(self):
        """Inline is for PersonAttribute model."""
        assert PersonAttributeInline.model is PersonAttribute

    def test_inline_extra_is_zero(self):
        """Inline does not show empty extra rows by default."""
        assert PersonAttributeInline.extra == 0

    def test_all_fields_readonly(self):
        """All displayed fields should be read-only."""
        assert set(PersonAttributeInline.fields) == set(PersonAttributeInline.readonly_fields)

    def test_value_type_in_fields(self):
        """value_type should appear in the inline fields."""
        assert "value_type" in PersonAttributeInline.fields


class TestPersonAttributeAdmin:
    """Tests for PersonAttributeAdmin configuration."""

    def test_list_display(self):
        admin = PersonAttributeAdmin(PersonAttribute, AdminSite())
        for col in ("person", "source", "key", "value", "value_type", "confidence", "created_at"):
            assert col in admin.list_display

    def test_list_filter(self):
        admin = PersonAttributeAdmin(PersonAttribute, AdminSite())
        for f in ("source", "key", "value_type"):
            assert f in admin.list_filter


class TestAttributeLabelAdmin:
    """Tests for AttributeLabelAdmin configuration."""

    def test_list_display(self):
        admin = AttributeLabelAdmin(AttributeLabel, AdminSite())
        for col in ("value_type", "slug", "display", "sort_order", "is_active"):
            assert col in admin.list_display

    def test_list_filter(self):
        admin = AttributeLabelAdmin(AttributeLabel, AdminSite())
        assert "value_type" in admin.list_filter
        assert "is_active" in admin.list_filter


class TestExternalPlatformAdmin:
    """Tests for ExternalPlatformAdmin configuration."""

    def test_list_display(self):
        admin = ExternalPlatformAdmin(ExternalPlatform, AdminSite())
        for col in ("slug", "display", "sort_order", "is_active"):
            assert col in admin.list_display

    def test_list_filter(self):
        admin = ExternalPlatformAdmin(ExternalPlatform, AdminSite())
        assert "is_active" in admin.list_filter


@pytest.mark.django_db
class TestPersonAdminIntegration:
    """Integration tests for admin with real data."""

    def test_person_registered_in_admin(self):
        """Person model is registered in the admin site."""
        assert Person in admin_site._registry

    def test_person_name_not_registered_standalone(self):
        """PersonName should only be available as inline, not standalone."""
        assert PersonName not in admin_site._registry

    def test_attribute_label_registered_in_admin(self):
        """AttributeLabel model is registered in the admin site."""
        assert AttributeLabel in admin_site._registry

    def test_external_platform_registered_in_admin(self):
        """ExternalPlatform model is registered in the admin site."""
        assert ExternalPlatform in admin_site._registry

    def test_person_attribute_registered_in_admin(self):
        """PersonAttribute model is registered standalone in the admin site."""
        assert PersonAttribute in admin_site._registry
