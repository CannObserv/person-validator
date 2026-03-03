"""Provider registry for the enrichment framework."""

from src.core.enrichment.base import Provider


class ProviderRegistry:
    """Registry that holds and manages enrichment providers.

    Providers can be registered, enabled, and disabled by name.
    Only enabled providers are returned by :meth:`enabled_providers`.
    """

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}
        self._enabled: dict[str, bool] = {}

    def register(self, provider: Provider, *, enabled: bool = True) -> None:
        """Register a provider instance.

        Raises ValueError if a provider with the same name is already registered.
        """
        if provider.name in self._providers:
            raise ValueError(f"Provider '{provider.name}' is already registered.")
        self._providers[provider.name] = provider
        self._enabled[provider.name] = enabled

    def get(self, name: str) -> Provider:
        """Retrieve a provider by name. Raises KeyError if not found."""
        return self._providers[name]

    def enable(self, name: str) -> None:
        """Enable a registered provider by name."""
        if name not in self._providers:
            raise KeyError(f"Provider '{name}' is not registered.")
        self._enabled[name] = True

    def disable(self, name: str) -> None:
        """Disable a registered provider by name."""
        if name not in self._providers:
            raise KeyError(f"Provider '{name}' is not registered.")
        self._enabled[name] = False

    def is_enabled(self, name: str) -> bool:
        """Return True if the named provider is enabled."""
        return self._enabled.get(name, False)

    def enabled_providers(self) -> list[Provider]:
        """Return all currently enabled providers in registration order."""
        return [p for name, p in self._providers.items() if self._enabled[name]]

    def all_providers(self) -> list[Provider]:
        """Return all registered providers regardless of enabled state."""
        return list(self._providers.values())
