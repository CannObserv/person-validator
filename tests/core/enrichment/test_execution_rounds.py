"""Tests for _resolve_execution_rounds — topological sort for provider dependency graph."""

import pytest

from src.core.enrichment.base import (
    CircularDependencyError,
    Dependency,
    EnrichmentResult,
    PersonData,
    Provider,
)
from src.core.enrichment.runner import _resolve_execution_rounds


def _make_provider(name: str, deps=None, outputs=None) -> Provider:
    """Factory: create a Provider with given name, deps, and output_keys."""

    class _P(Provider):
        dependencies = deps or []
        output_keys = outputs or []

        def enrich(self, person: PersonData) -> list[EnrichmentResult]:
            return []

    _P.name = name
    return _P()


class TestResolveExecutionRoundsNoDependencies:
    """All providers independent → single round."""

    def test_empty_list_returns_empty(self):
        assert _resolve_execution_rounds([]) == []

    def test_single_provider_one_round(self):
        p = _make_provider("a")
        rounds = _resolve_execution_rounds([p])
        assert rounds == [[p]]

    def test_multiple_independent_single_round(self):
        a = _make_provider("a")
        b = _make_provider("b")
        c = _make_provider("c")
        rounds = _resolve_execution_rounds([a, b, c])
        assert len(rounds) == 1
        assert set(rounds[0]) == {a, b, c}


class TestResolveExecutionRoundsLinearChain:
    """A produces key_a, B depends on key_a and produces key_b, C depends on key_b."""

    def test_linear_chain_three_rounds(self):
        a = _make_provider("a", outputs=["key_a"])
        b = _make_provider("b", deps=[Dependency(attribute_key="key_a")], outputs=["key_b"])
        c = _make_provider("c", deps=[Dependency(attribute_key="key_b")])
        rounds = _resolve_execution_rounds([a, b, c])
        assert len(rounds) == 3
        assert rounds[0] == [a]
        assert rounds[1] == [b]
        assert rounds[2] == [c]

    def test_linear_chain_order_independent_of_registration(self):
        """Topological sort works regardless of registration order."""
        a = _make_provider("a", outputs=["key_a"])
        b = _make_provider("b", deps=[Dependency(attribute_key="key_a")], outputs=["key_b"])
        c = _make_provider("c", deps=[Dependency(attribute_key="key_b")])
        # Register in reverse order
        rounds = _resolve_execution_rounds([c, b, a])
        assert len(rounds) == 3
        assert rounds[0] == [a]
        assert rounds[1] == [b]
        assert rounds[2] == [c]


class TestResolveExecutionRoundsDiamond:
    """Diamond: A → B, A → C, B → D, C → D."""

    def test_diamond_three_rounds(self):
        a = _make_provider("a", outputs=["key_a"])
        b = _make_provider("b", deps=[Dependency(attribute_key="key_a")], outputs=["key_b"])
        c = _make_provider("c", deps=[Dependency(attribute_key="key_a")], outputs=["key_c"])
        d = _make_provider(
            "d",
            deps=[
                Dependency(attribute_key="key_b"),
                Dependency(attribute_key="key_c"),
            ],
        )
        rounds = _resolve_execution_rounds([a, b, c, d])
        assert len(rounds) == 3
        assert rounds[0] == [a]
        assert set(rounds[1]) == {b, c}
        assert rounds[2] == [d]


class TestResolveExecutionRoundsCycle:
    """Circular dependencies raise CircularDependencyError."""

    def test_two_node_cycle(self):
        a = _make_provider("a", deps=[Dependency(attribute_key="key_b")], outputs=["key_a"])
        b = _make_provider("b", deps=[Dependency(attribute_key="key_a")], outputs=["key_b"])
        with pytest.raises(CircularDependencyError):
            _resolve_execution_rounds([a, b])

    def test_self_cycle(self):
        """A provider that depends on its own output."""
        a = _make_provider("a", deps=[Dependency(attribute_key="key_a")], outputs=["key_a"])
        with pytest.raises(CircularDependencyError):
            _resolve_execution_rounds([a])

    def test_three_node_cycle(self):
        a = _make_provider("a", deps=[Dependency(attribute_key="key_c")], outputs=["key_a"])
        b = _make_provider("b", deps=[Dependency(attribute_key="key_a")], outputs=["key_b"])
        c = _make_provider("c", deps=[Dependency(attribute_key="key_b")], outputs=["key_c"])
        with pytest.raises(CircularDependencyError):
            _resolve_execution_rounds([a, b, c])

    def test_skip_if_absent_false_still_participates_in_graph(self):
        """Deps with skip_if_absent=False still create ordering edges."""
        a = _make_provider(
            "a",
            deps=[Dependency(attribute_key="key_b", skip_if_absent=False)],
            outputs=["key_a"],
        )
        b = _make_provider("b", deps=[Dependency(attribute_key="key_a")], outputs=["key_b"])
        with pytest.raises(CircularDependencyError):
            _resolve_execution_rounds([a, b])


class TestResolveExecutionRoundsUnresolvedDep:
    """Dep key with no registered producer logs a debug message."""

    def test_unresolved_dep_logs_debug(self):
        from unittest.mock import patch

        a = _make_provider("a", deps=[Dependency(attribute_key="wikidata_qid")])
        with patch("src.core.enrichment.runner.logger") as mock_logger:
            _resolve_execution_rounds([a])
        debug_messages = [str(call) for call in mock_logger.debug.call_args_list]
        assert any("wikidata_qid" in msg for msg in debug_messages)

    def test_unresolved_dep_does_not_raise(self):
        """Provider with an unresolved dep is placed in round 0; can_run() handles it."""
        a = _make_provider("a", deps=[Dependency(attribute_key="wikidata_qid")])
        rounds = _resolve_execution_rounds([a])
        assert len(rounds) == 1
        assert rounds[0] == [a]


class TestResolveExecutionRoundsMixedGraph:
    """Some providers independent, some chained."""

    def test_independent_plus_chain(self):
        """standalone runs in round 1 alongside a; b is round 2."""
        standalone = _make_provider("standalone")
        a = _make_provider("a", outputs=["key_a"])
        b = _make_provider("b", deps=[Dependency(attribute_key="key_a")])
        rounds = _resolve_execution_rounds([standalone, a, b])
        assert len(rounds) == 2
        assert set(rounds[0]) == {standalone, a}
        assert rounds[1] == [b]
