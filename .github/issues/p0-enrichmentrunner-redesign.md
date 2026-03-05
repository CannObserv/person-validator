## Context

The current `EnrichmentRunner` iterates providers sequentially with no dependency awareness. The enrichment system requires:

1. **Provider dependencies**: some providers require an attribute produced by a prior provider (e.g. `WikipediaProvider` needs `wikidata_qid` written by `WikidataProvider`)
2. **Parallel execution**: independent providers should run concurrently
3. **Configurable skip behaviour**: when a dependency is unmet, downstream providers are skipped by default but this is configurable
4. **Run history**: every provider run is logged to `EnrichmentRun` (see Phase 0 issue)

This issue redesigns `src/core/enrichment/base.py`, `src/core/enrichment/runner.py`, and `src/core/enrichment/registry.py` to implement these capabilities.

## Changes to `base.py`

### `Dependency` dataclass

```python
@dataclass
class Dependency:
    """Declares that a provider requires a specific attribute key to be present.

    Args:
        attribute_key: The PersonAttribute.key value that must exist for this
            person before this provider can run.
        skip_if_absent: If True (default), the provider is skipped entirely
            when the dependency attribute is not present. If False, the provider
            still runs; it must handle absence gracefully via the
            existing_attributes field on PersonData.
    """
    attribute_key: str
    skip_if_absent: bool = True
```

### Updated `Provider` ABC

```python
class Provider(ABC):
    name: str
    dependencies: list[Dependency] = []
    refresh_interval: timedelta = timedelta(days=7)

    def can_run(self, existing_attribute_keys: set[str]) -> bool:
        """Return True if all skip_if_absent dependencies are satisfied."""
        return all(
            dep.attribute_key in existing_attribute_keys
            for dep in self.dependencies
            if dep.skip_if_absent
        )

    @abstractmethod
    def enrich(self, person: PersonData) -> list[EnrichmentResult]:
        ...
```

### Updated `PersonData`

```python
@dataclass
class PersonData:
    id: str
    name: str
    given_name: str | None = None
    middle_name: str | None = None
    surname: str | None = None
    existing_attributes: list[dict] = field(default_factory=list)
    # Each dict has keys: key (str), value (str), value_type (str), source (str)
    # Populated by EnrichmentRunner from the DB before running providers.

    def attribute_keys(self) -> set[str]:
        """Return the set of attribute keys currently on this person."""
        return {a["key"] for a in self.existing_attributes}
```

### `CircularDependencyError`

```python
class CircularDependencyError(Exception):
    """Raised when provider dependencies contain a cycle."""
```

## Changes to `runner.py`

### Topological sort

```python
def _resolve_execution_rounds(providers: list[Provider]) -> list[list[Provider]]:
    """
    Topological sort of providers by dependency graph.

    Returns a list of rounds. Providers within a round have no inter-dependencies
    and can run in parallel. Providers in round N+1 depend on output from round N.

    Raises CircularDependencyError if a dependency cycle is detected.

    Algorithm: Kahn's algorithm (BFS-based topological sort).
    - Build adjacency: for each provider B that depends on attribute key K,
      find all providers A that could produce K (i.e. providers whose enrich()
      is documented to write key K). 
    - Edge: A -> B (A must precede B).
    - Note: dependency edges are attribute-key-based, not provider-name-based.
      A provider declares dep on a key; the runner resolves which provider(s)
      produce that key by checking provider.output_keys (see below).
    """
```

### `output_keys` on Provider

Each provider must declare which attribute keys it writes, so the runner can build the dependency graph:

```python
class Provider(ABC):
    output_keys: list[str] = []
    # Example: WikidataProvider.output_keys = ["wikidata_qid", "wikidata_url"]
```

### Parallel execution

Each round is executed with `concurrent.futures.ThreadPoolExecutor`:

```python
with ThreadPoolExecutor(max_workers=min(len(round_providers), 8)) as executor:
    futures = {
        executor.submit(_run_single_provider, provider, person, triggered_by): provider
        for provider in round_providers
        if provider.can_run(person.attribute_keys())
    }
    for future in as_completed(futures):
        provider = futures[future]
        try:
            run_result = future.result()
        except Exception:
            logger.exception("Provider '%s' failed", provider.name)
```

After each round completes, `person.existing_attributes` is refreshed from the DB so that the next round's `can_run()` checks see newly-written attributes.

### Skipped providers

If `provider.can_run()` returns False, create an `EnrichmentRun` with `status="skipped"` and do not call `provider.enrich()`.

### `EnrichmentRunner.run()` signature update

```python
def run(
    self,
    person: PersonData,
    *,
    triggered_by: str = "manual",
    provider_names: list[str] | None = None,  # None = run all enabled
) -> dict[str, EnrichmentRunResult]:
    """
    Run providers against a person.

    Returns a dict mapping provider name to EnrichmentRunResult.
    """
```

## `SocialPlatform` → `ExternalPlatform` in runner

`_load_active_platforms()` must import `ExternalPlatform` (not `SocialPlatform`). This change is contingent on the rename issue being merged first.

## Test requirements

- Test `_resolve_execution_rounds` with:
  - Linear chain (A → B → C)
  - Diamond (A → B, A → C, B → D, C → D)
  - No dependencies (all parallel)
  - Cycle (raises `CircularDependencyError`)
- Test `Provider.can_run()` with satisfied/unsatisfied deps and `skip_if_absent=False`
- Test parallel round execution (mock providers that record call order/timing)
- Test that `existing_attributes` is refreshed between rounds
- Test skipped provider creates `EnrichmentRun(status="skipped")`

## Acceptance criteria

- [ ] `Dependency` dataclass in `base.py`
- [ ] `Provider.dependencies`, `Provider.output_keys`, `Provider.refresh_interval` 
- [ ] `Provider.can_run()` works correctly for all cases
- [ ] `PersonData.existing_attributes` and `PersonData.attribute_keys()`
- [ ] `CircularDependencyError` raised on cycles
- [ ] Topological sort produces correct rounds for all graph shapes
- [ ] Within-round providers run in parallel via `ThreadPoolExecutor`
- [ ] `existing_attributes` refreshed between rounds
- [ ] Skipped providers logged to `EnrichmentRun`
- [ ] `triggered_by` parameter plumbed through
- [ ] All existing tests pass; new tests cover all graph shapes and edge cases
