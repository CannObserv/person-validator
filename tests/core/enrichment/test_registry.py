"""Tests for the ProviderRegistry."""

import pytest

from src.core.enrichment.base import EnrichmentResult, PersonData, Provider
from src.core.enrichment.registry import ProviderRegistry


def _make_provider(name: str) -> Provider:
    class _P(Provider):
        def enrich(self, person: PersonData) -> list[EnrichmentResult]:
            return []

    _P.name = name
    return _P()


class TestProviderRegistry:
    """Tests for ProviderRegistry."""

    def test_register_and_retrieve(self):
        reg = ProviderRegistry()
        p = _make_provider("acme")
        reg.register(p)
        assert reg.get("acme") is p

    def test_get_unknown_raises(self):
        reg = ProviderRegistry()
        with pytest.raises(KeyError):
            reg.get("missing")

    def test_duplicate_registration_raises(self):
        reg = ProviderRegistry()
        reg.register(_make_provider("dupe"))
        with pytest.raises(ValueError, match="already registered"):
            reg.register(_make_provider("dupe"))

    def test_enabled_by_default(self):
        reg = ProviderRegistry()
        reg.register(_make_provider("p1"))
        assert reg.is_enabled("p1") is True

    def test_register_disabled(self):
        reg = ProviderRegistry()
        reg.register(_make_provider("p1"), enabled=False)
        assert reg.is_enabled("p1") is False

    def test_enable_and_disable(self):
        reg = ProviderRegistry()
        reg.register(_make_provider("p1"))
        reg.disable("p1")
        assert reg.is_enabled("p1") is False
        reg.enable("p1")
        assert reg.is_enabled("p1") is True

    def test_enable_unknown_raises(self):
        reg = ProviderRegistry()
        with pytest.raises(KeyError):
            reg.enable("missing")

    def test_disable_unknown_raises(self):
        reg = ProviderRegistry()
        with pytest.raises(KeyError):
            reg.disable("missing")

    def test_enabled_providers_excludes_disabled(self):
        reg = ProviderRegistry()
        p1 = _make_provider("p1")
        p2 = _make_provider("p2")
        reg.register(p1)
        reg.register(p2, enabled=False)
        assert reg.enabled_providers() == [p1]

    def test_enabled_providers_order(self):
        reg = ProviderRegistry()
        names = ["c", "a", "b"]
        providers = {n: _make_provider(n) for n in names}
        for p in providers.values():
            reg.register(p)
        assert [p.name for p in reg.enabled_providers()] == names

    def test_all_providers_includes_disabled(self):
        reg = ProviderRegistry()
        p1 = _make_provider("p1")
        p2 = _make_provider("p2")
        reg.register(p1)
        reg.register(p2, enabled=False)
        assert set(reg.all_providers()) == {p1, p2}
