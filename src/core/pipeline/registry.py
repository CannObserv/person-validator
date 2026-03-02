"""Stage registry for configuration-driven pipeline assembly."""

from __future__ import annotations

from typing import Any

from src.core.pipeline.base import Pipeline, Stage


class StageRegistry:
    """Registry that maps names to Stage classes and their default configs.

    Usage::

        registry = StageRegistry()
        registry.register("basic", BasicNormalization)
        pipeline = registry.build_pipeline(["basic"])
    """

    def __init__(self) -> None:
        self._entries: dict[str, tuple[type[Stage], dict[str, Any]]] = {}

    def register(
        self,
        name: str,
        cls: type[Stage],
        *,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Register *cls* under *name* with optional default *config*."""
        self._entries[name] = (cls, config or {})

    def build_stage(self, name: str) -> Stage:
        """Instantiate the stage registered as *name*.

        Raises:
            KeyError: if *name* is not registered.
        """
        if name not in self._entries:
            raise KeyError(f"unknown stage: {name!r}")
        cls, config = self._entries[name]
        # config keys must match the keyword arguments accepted by cls.__init__.
        return cls(**config) if config else cls()

    def build_pipeline(self, names: list[str]) -> Pipeline:
        """Build a Pipeline from an ordered list of registered stage names."""
        stages = [self.build_stage(n) for n in names]
        return Pipeline(stages=stages)
