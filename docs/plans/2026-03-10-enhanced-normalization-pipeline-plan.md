# Enhanced Normalization Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the `/v1/find` pipeline with weighted variant generation, name cleaning/classification, and four new stages (InputClassification, NameParsing, NicknameExpansion, TitleExtraction).

**Architecture:** `PipelineResult` gains `WeightedVariant` variants, `messages`, and `is_valid_name`. The matching layer multiplies base DB certainty by variant weight. Four new pipeline stages run after `BasicNormalization` to clean input, parse name components, and generate weighted alternative search strings. Stage order: `InputClassification → BasicNormalization → NameParsing → NicknameExpansion → TitleExtraction`. InputClassification runs first so that its cleaned output (e.g. extracted email names) is subsequently lowercased by BasicNormalization before reaching the matching layer.

**Tech Stack:** Python 3.12, pytest, `nameparser` (PyPI), `nicknames` (PyPI), SQLite, FastAPI, Pydantic. All commands run from the worktree root: `.worktrees/enhanced-normalization-pipeline/`. Tests require env vars: `export $(grep -v '^#' ../../env | xargs)`.

---

## Task 1: `WeightedVariant` + `PipelineResult` structural changes

**Files:**
- Modify: `src/core/pipeline/base.py`
- Modify: `src/core/pipeline/stages.py`
- Modify: `src/core/pipeline/__init__.py`
- Modify: `tests/core/test_pipeline.py`

### Step 1: Write the failing tests

In `tests/core/test_pipeline.py`, replace the file contents with:

```python
"""Tests for src.core.pipeline — PipelineResult, WeightedVariant, Stage, Pipeline, registry, BasicNormalization."""

import pytest

from src.core.pipeline import (
    BasicNormalization,
    Pipeline,
    PipelineResult,
    Stage,
    StageRegistry,
    WeightedVariant,
)


class TestWeightedVariant:
    """Tests for WeightedVariant dataclass."""

    def test_construction(self):
        v = WeightedVariant(name="bob smith", weight=0.85)
        assert v.name == "bob smith"
        assert v.weight == 0.85

    def test_immutable(self):
        v = WeightedVariant(name="bob smith", weight=0.85)
        with pytest.raises((AttributeError, TypeError)):
            v.name = "other"  # type: ignore[misc]


class TestPipelineResult:
    """Tests for PipelineResult dataclass."""

    def test_construction_minimal(self):
        r = PipelineResult(original="Bob Smith", resolved="bob smith")
        assert r.original == "Bob Smith"
        assert r.resolved == "bob smith"
        assert r.variants == []
        assert r.messages == []
        assert r.is_valid_name is None

    def test_construction_full(self):
        v = WeightedVariant(name="robert smith", weight=0.9)
        r = PipelineResult(
            original="Bob Smith",
            resolved="bob smith",
            variants=[v],
            messages=["Prefix stripped: Mr."],
            is_valid_name=True,
        )
        assert r.variants == [v]
        assert r.messages == ["Prefix stripped: Mr."]
        assert r.is_valid_name is True

    def test_variants_default_independent(self):
        r1 = PipelineResult(original="A", resolved="a")
        r2 = PipelineResult(original="B", resolved="b")
        r1.variants.append(WeightedVariant(name="a", weight=1.0))
        assert r2.variants == []

    def test_messages_default_independent(self):
        r1 = PipelineResult(original="A", resolved="a")
        r2 = PipelineResult(original="B", resolved="b")
        r1.messages.append("warning")
        assert r2.messages == []


class TestPipelineZeroStages:
    """Pipeline with no stages returns original input unchanged."""

    def test_empty_pipeline_returns_original(self):
        pipeline = Pipeline(stages=[])
        result = pipeline.run("Alice Jones")
        assert result.original == "Alice Jones"
        assert result.resolved == "Alice Jones"
        assert result.variants == []
        assert result.messages == []
        assert result.is_valid_name is None


class DummyUpperStage(Stage):
    """Test stage that uppercases resolved."""

    def process(self, result: PipelineResult) -> PipelineResult:
        return PipelineResult(
            original=result.original,
            resolved=result.resolved.upper(),
            variants=list(result.variants),
            messages=list(result.messages),
            is_valid_name=result.is_valid_name,
        )


class DummyAppendStage(Stage):
    """Test stage that appends a fixed WeightedVariant."""

    def __init__(self, variant_name: str, weight: float = 1.0) -> None:
        self.variant_name = variant_name
        self.weight = weight

    def process(self, result: PipelineResult) -> PipelineResult:
        return PipelineResult(
            original=result.original,
            resolved=result.resolved,
            variants=[*result.variants, WeightedVariant(name=self.variant_name, weight=self.weight)],
            messages=list(result.messages),
            is_valid_name=result.is_valid_name,
        )


class TestPipelineOrdering:
    """Earlier stages feed into later stages."""

    def test_stages_run_in_order(self):
        pipeline = Pipeline(stages=[DummyAppendStage("first"), DummyAppendStage("second")])
        result = pipeline.run("x")
        assert [v.name for v in result.variants] == ["first", "second"]

    def test_later_stage_sees_earlier_resolved(self):
        pipeline = Pipeline(stages=[DummyUpperStage(), DummyAppendStage("appended")])
        result = pipeline.run("hello")
        assert result.resolved == "HELLO"
        assert any(v.name == "appended" for v in result.variants)


class TestStageRegistry:
    """Stage registry: register, retrieve, build pipeline from names."""

    def test_register_and_retrieve(self):
        registry = StageRegistry()
        registry.register("upper", DummyUpperStage)
        stage = registry.build_stage("upper")
        assert isinstance(stage, DummyUpperStage)

    def test_build_pipeline_from_names(self):
        registry = StageRegistry()
        registry.register("upper", DummyUpperStage)
        registry.register("append", DummyAppendStage, config={"variant_name": "v"})
        pipeline = registry.build_pipeline(["upper", "append"])
        result = pipeline.run("hello")
        assert result.resolved == "HELLO"
        assert any(v.name == "v" for v in result.variants)

    def test_unknown_stage_raises(self):
        registry = StageRegistry()
        with pytest.raises(KeyError, match="unknown"):
            registry.build_stage("unknown")

    def test_register_overwrites(self):
        registry = StageRegistry()
        registry.register("s", DummyUpperStage)
        registry.register("s", DummyAppendStage, config={"variant_name": "x"})
        stage = registry.build_stage("s")
        assert isinstance(stage, DummyAppendStage)


class TestBasicNormalization:
    """Tests for the BasicNormalization stage."""

    def _run(self, name: str) -> PipelineResult:
        pipeline = Pipeline(stages=[BasicNormalization()])
        return pipeline.run(name)

    def test_lowercases_resolved(self):
        result = self._run("Robert Smith")
        assert result.resolved == "robert smith"

    def test_collapses_whitespace(self):
        result = self._run("  Bob   Smith  ")
        assert result.resolved == "bob smith"

    def test_removes_periods(self):
        result = self._run("Jr.")
        assert result.resolved == "jr"

    def test_removes_commas(self):
        result = self._run("Smith, Jane")
        assert result.resolved == "smith jane"

    def test_preserves_hyphens(self):
        result = self._run("Mary-Jane Watson")
        assert result.resolved == "mary-jane watson"

    def test_does_not_append_variants(self):
        result = self._run("Robert Smith")
        assert result.variants == []

    def test_passes_through_messages(self):
        """BasicNormalization preserves messages set by earlier stages."""
        stage = BasicNormalization()
        r = PipelineResult(
            original="Bob",
            resolved="Bob",
            messages=["prior message"],
        )
        result = stage.process(r)
        assert result.messages == ["prior message"]

    def test_passes_through_is_valid_name(self):
        stage = BasicNormalization()
        r = PipelineResult(original="Bob", resolved="Bob", is_valid_name=False)
        result = stage.process(r)
        assert result.is_valid_name is False

    def test_strips_underscores(self):
        result = self._run("bob_smith")
        assert result.resolved == "bobsmith"

    def test_original_preserved(self):
        result = self._run("Robert Smith")
        assert result.original == "Robert Smith"

    def test_empty_string(self):
        result = self._run("")
        assert result.resolved == ""
        assert result.variants == []
```

### Step 2: Run tests to confirm they fail

```bash
uv run pytest tests/core/test_pipeline.py -v 2>&1 | head -40
```

Expected: FAIL — `WeightedVariant` not importable, `PipelineResult` missing `messages`/`is_valid_name`.

### Step 3: Update `src/core/pipeline/base.py`

Replace the file:

```python
"""Core pipeline data structures: PipelineResult, WeightedVariant, Stage, Pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class WeightedVariant:
    """A name variant paired with a confidence weight.

    Attributes:
        name: The normalized name string to search against.
        weight: Multiplier applied to base certainty from the DB match.
                1.0 = full confidence; lower values reduce final certainty.
    """

    name: str
    weight: float


@dataclass
class PipelineResult:
    """The result produced by running a name through a Pipeline.

    Attributes:
        original: The raw input string, never modified.
        resolved: The best normalized form (primary candidate).
        variants: Weighted alternative strings to attempt matching on.
        messages: Soft warnings or informational notes about the input.
        is_valid_name: True/False when a stage is confident; None if not yet assessed.
    """

    original: str
    resolved: str
    variants: list[WeightedVariant] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    is_valid_name: bool | None = None


class Stage(ABC):
    """Abstract base class for a pipeline stage.

    Each stage receives the current PipelineResult and returns a
    (possibly modified) PipelineResult. Stages must not mutate the
    incoming result in-place; they should return a new instance.

    Stages must propagate all fields they do not modify:
    ``original``, ``messages``, and ``is_valid_name`` are pass-through
    unless the stage explicitly changes them.
    """

    @abstractmethod
    def process(self, result: PipelineResult) -> PipelineResult:
        """Process *result* and return a new PipelineResult."""
        ...


class Pipeline:
    """An ordered chain of Stage instances."""

    def __init__(self, stages: list[Stage]) -> None:
        self.stages = stages

    def run(self, name: str) -> PipelineResult:
        """Run *name* through all stages and return the final PipelineResult."""
        result = PipelineResult(original=name, resolved=name)
        for stage in self.stages:
            result = stage.process(result)
        return result
```

### Step 4: Update `src/core/pipeline/stages.py`

Replace the file:

```python
"""Concrete pipeline stages."""

from __future__ import annotations

import re

from src.core.pipeline.base import PipelineResult, Stage

# Matches characters to remove: everything except ASCII letters, whitespace, hyphens.
_STRIP_RE = re.compile(r"[^a-zA-Z\s-]")
# Collapse runs of whitespace (including tabs/newlines)
_SPACE_RE = re.compile(r"\s+")


class BasicNormalization(Stage):
    """Minimal normalization stage.

    Transforms the resolved name by:
    - Lowercasing
    - Removing characters other than ASCII letters, whitespace, and hyphens
    - Collapsing whitespace and stripping leading/trailing space

    This stage only updates ``resolved``; it never appends to ``variants``.
    It passes ``messages`` and ``is_valid_name`` through unchanged.
    """

    def process(self, result: PipelineResult) -> PipelineResult:
        """Return a new PipelineResult with the normalized resolved name."""
        normalized = result.resolved.lower()
        normalized = _STRIP_RE.sub("", normalized)
        normalized = _SPACE_RE.sub(" ", normalized).strip()

        return PipelineResult(
            original=result.original,
            resolved=normalized,
            variants=list(result.variants),
            messages=list(result.messages),
            is_valid_name=result.is_valid_name,
        )
```

### Step 5: Update `src/core/pipeline/__init__.py`

```python
"""Name normalization pipeline framework.

Public API:
    WeightedVariant     — name + confidence weight pair
    PipelineResult      — dataclass produced by Pipeline.run()
    Stage               — abstract base for pipeline stages
    Pipeline            — ordered chain of Stage instances
    StageRegistry       — named registry for building pipelines from config
    BasicNormalization  — first concrete stage (lowercase, whitespace, punctuation)
"""

from src.core.pipeline.base import Pipeline, PipelineResult, Stage, WeightedVariant
from src.core.pipeline.registry import StageRegistry
from src.core.pipeline.stages import BasicNormalization

__all__ = [
    "BasicNormalization",
    "Pipeline",
    "PipelineResult",
    "Stage",
    "StageRegistry",
    "WeightedVariant",
]
```

### Step 6: Run tests to confirm they pass

```bash
uv run pytest tests/core/test_pipeline.py -v
```

Expected: all pass.

### Step 7: Commit

```bash
git add src/core/pipeline/base.py src/core/pipeline/stages.py src/core/pipeline/__init__.py tests/core/test_pipeline.py
git commit -m "feat: add WeightedVariant and extend PipelineResult with messages/is_valid_name"
```

---

## Task 2: Update `matching.py` to accept `WeightedVariant`

**Files:**
- Modify: `src/core/matching.py`
- Create: `tests/core/test_matching.py`

### Step 1: Write the failing tests

Create `tests/core/test_matching.py`:

```python
"""Tests for src.core.matching — normalize() and search()."""

import sqlite3

import pytest

from src.core.matching import normalize, search
from src.core.pipeline.base import WeightedVariant


@pytest.fixture
def conn(tmp_path):
    """In-memory SQLite connection with minimal schema for matching tests."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE persons_person (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL
        );
        CREATE TABLE persons_personname (
            id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL,
            full_name TEXT NOT NULL,
            given_name TEXT,
            surname TEXT,
            name_type TEXT NOT NULL DEFAULT 'primary',
            is_primary INTEGER NOT NULL DEFAULT 0
        );
    """)
    return db


def insert_person(conn, pid, name):
    conn.execute("INSERT INTO persons_person (id, name) VALUES (?, ?)", (pid, name))
    conn.commit()


def insert_name(conn, nid, pid, full_name, given_name=None, surname=None, name_type="primary", is_primary=True):
    conn.execute(
        "INSERT INTO persons_personname"
        " (id, person_id, full_name, given_name, surname, name_type, is_primary)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (nid, pid, full_name, given_name, surname, name_type, int(is_primary)),
    )
    conn.commit()


class TestNormalize:
    def test_lowercases(self):
        assert normalize("Bob Smith") == "bob smith"

    def test_strips_non_alpha(self):
        assert normalize("Dr. Smith") == "dr smith"

    def test_collapses_whitespace(self):
        assert normalize("  Bob   Smith  ") == "bob smith"


class TestSearchExactMatch:
    def test_primary_exact_match_certainty_1(self, conn):
        insert_person(conn, "p1", "Alice Jones")
        insert_name(conn, "n1", "p1", "Alice Jones", "Alice", "Jones", is_primary=True)
        results = search(conn, [WeightedVariant(name="alice jones", weight=1.0)])
        assert len(results) == 1
        assert results[0].person_id == "p1"
        assert results[0].certainty == pytest.approx(1.0)

    def test_non_primary_exact_match_certainty_09(self, conn):
        insert_person(conn, "p1", "Alice Jones")
        insert_name(conn, "n1", "p1", "Alice Jones", "Alice", "Jones", name_type="alias", is_primary=False)
        results = search(conn, [WeightedVariant(name="alice jones", weight=1.0)])
        assert results[0].certainty == pytest.approx(0.9)

    def test_weight_multiplies_base_certainty(self, conn):
        insert_person(conn, "p1", "Alice Jones")
        insert_name(conn, "n1", "p1", "Alice Jones", "Alice", "Jones", is_primary=True)
        results = search(conn, [WeightedVariant(name="alice jones", weight=0.85)])
        assert results[0].certainty == pytest.approx(1.0 * 0.85)

    def test_empty_variants_returns_empty(self, conn):
        assert search(conn, []) == []


class TestSearchPairMatch:
    def test_pair_match_primary_certainty_08(self, conn):
        insert_person(conn, "p1", "Alice Marie Jones")
        insert_name(conn, "n1", "p1", "Alice Marie Jones", "Alice", "Jones", is_primary=True)
        results = search(conn, [WeightedVariant(name="alice jones", weight=1.0)])
        assert results[0].certainty == pytest.approx(0.8)

    def test_pair_match_weight_applied(self, conn):
        insert_person(conn, "p1", "Alice Marie Jones")
        insert_name(conn, "n1", "p1", "Alice Marie Jones", "Alice", "Jones", is_primary=True)
        results = search(conn, [WeightedVariant(name="alice jones", weight=0.85)])
        assert results[0].certainty == pytest.approx(0.8 * 0.85)

    def test_exact_match_takes_priority_over_pair(self, conn):
        insert_person(conn, "p1", "Alice Jones")
        insert_name(conn, "n1", "p1", "Alice Jones", "Alice", "Jones", is_primary=True)
        # One variant is exact (weight 1.0), would also produce a pair match
        results = search(conn, [WeightedVariant(name="alice jones", weight=1.0)])
        assert results[0].certainty == pytest.approx(1.0)

    def test_max_weight_used_when_multiple_variants_produce_same_pair(self, conn):
        insert_person(conn, "p1", "Alice Marie Jones")
        insert_name(conn, "n1", "p1", "Alice Marie Jones", "Alice", "Jones", is_primary=True)
        variants = [
            WeightedVariant(name="alice jones", weight=0.7),
            WeightedVariant(name="alice j jones", weight=0.9),
        ]
        results = search(conn, variants)
        # Both produce pair (alice, jones); max weight 0.9 should be used
        assert results[0].certainty == pytest.approx(0.8 * 0.9)


class TestSearchSorting:
    def test_results_sorted_by_certainty_descending(self, conn):
        insert_person(conn, "p1", "Alice Jones")
        insert_name(conn, "n1", "p1", "Alice Jones", "Alice", "Jones", is_primary=True)
        insert_person(conn, "p2", "Alice Marie Jones")
        insert_name(conn, "n2", "p2", "Alice Marie Jones", "Alice", "Jones", is_primary=True)

        results = search(conn, [WeightedVariant(name="alice jones", weight=1.0)])
        certainties = [r.certainty for r in results]
        assert certainties == sorted(certainties, reverse=True)
```

### Step 2: Run tests to confirm they fail

```bash
uv run pytest tests/core/test_matching.py -v 2>&1 | head -30
```

Expected: FAIL — `search()` does not accept `WeightedVariant`.

### Step 3: Update `src/core/matching.py`

Replace the file:

```python
"""Name normalization and matching logic.

Pure domain functions for normalizing name queries and searching
PersonName records in the shared SQLite database. No API-layer
dependencies — returns plain dicts suitable for any caller.
"""

import re
import sqlite3
from dataclasses import dataclass

from src.core.pipeline.base import WeightedVariant

_NON_ALPHA_RE = re.compile(r"[^a-zA-Z\s]")
_MULTI_SPACE_RE = re.compile(r"\s+")


def normalize(name: str) -> str:
    """Lowercase, strip non-letter characters, and collapse whitespace."""
    text = name.lower()
    text = _NON_ALPHA_RE.sub("", text)
    text = _MULTI_SPACE_RE.sub(" ", text).strip()
    return text


@dataclass(frozen=True)
class MatchResult:
    """A single person match from the database."""

    person_id: str
    certainty: float
    full_name: str
    name_type: str


def search(conn: sqlite3.Connection, variants: list[WeightedVariant]) -> list[MatchResult]:
    """Search PersonName records for matches against weighted name variants.

    Executes two batch queries across all variants:
    1. Exact full_name match → base certainty 1.0 primary / 0.9 other
    2. given_name + surname pair match → base certainty 0.8 primary / 0.7 other

    Final certainty = base_certainty × variant.weight.

    Returns results sorted by certainty descending, one entry per person
    (highest certainty across all variants wins).
    """
    if not variants:
        return []

    weight_map = {v.name: v.weight for v in variants}
    variant_names = [v.name for v in variants]

    best: dict[str, MatchResult] = {}

    # 1. Batch exact full_name match
    placeholders = ",".join("?" * len(variant_names))
    rows = conn.execute(
        f"SELECT pn.full_name, pn.name_type, pn.is_primary, p.id AS person_id"
        f" FROM persons_personname pn"
        f" JOIN persons_person p ON p.id = pn.person_id"
        f" WHERE LOWER(pn.full_name) IN ({placeholders})",
        variant_names,
    ).fetchall()

    for row in rows:
        base = 1.0 if row["is_primary"] else 0.9
        weight = weight_map.get(row["full_name"].lower(), 1.0)
        certainty = base * weight
        pid = row["person_id"]
        if pid not in best or certainty > best[pid].certainty:
            best[pid] = MatchResult(
                person_id=pid,
                certainty=certainty,
                full_name=row["full_name"],
                name_type=row["name_type"],
            )

    # 2. Batch given_name + surname pair match.
    # For each pair, track the maximum weight across all variants that produce it.
    pair_weights: dict[tuple[str, str], float] = {}
    for v in variants:
        parts = v.name.split()
        if len(parts) >= 2:
            pair = (parts[0], parts[-1])
            pair_weights[pair] = max(pair_weights.get(pair, 0.0), v.weight)

    pairs = list(pair_weights.keys())

    if pairs:
        pair_clauses = " OR ".join(
            "(LOWER(pn.given_name) = ? AND LOWER(pn.surname) = ?)" for _ in pairs
        )
        params = [val for pair in pairs for val in pair]
        rows = conn.execute(
            f"SELECT pn.full_name, pn.name_type, pn.is_primary, p.id AS person_id,"
            f" pn.given_name, pn.surname"
            f" FROM persons_personname pn"
            f" JOIN persons_person p ON p.id = pn.person_id"
            f" WHERE {pair_clauses}",
            params,
        ).fetchall()

        for row in rows:
            pid = row["person_id"]
            if pid in best:
                continue
            base = 0.8 if row["is_primary"] else 0.7
            given = (row["given_name"] or "").lower()
            surname = (row["surname"] or "").lower()
            weight = pair_weights.get((given, surname), 1.0)
            certainty = base * weight
            best[pid] = MatchResult(
                person_id=pid,
                certainty=certainty,
                full_name=row["full_name"],
                name_type=row["name_type"],
            )

    return sorted(best.values(), key=lambda r: r.certainty, reverse=True)
```

### Step 4: Run tests

```bash
uv run pytest tests/core/test_matching.py -v
```

Expected: all pass.

### Step 5: Run full suite to catch regressions

```bash
uv run pytest --no-cov -q
```

The `tests/api/test_find.py` will fail because `search()` is now called with `list[str]` from the endpoint. That is expected — it will be fixed in Task 3.

### Step 6: Commit

```bash
git add src/core/matching.py tests/core/test_matching.py
git commit -m "feat: update search() to accept WeightedVariant with weight-multiplied certainty"
```

---

## Task 3: Update `schemas.py` and `v1.py`

**Files:**
- Modify: `src/api/schemas.py`
- Modify: `src/api/routes/v1.py`
- Modify: `tests/api/test_find.py`

### Step 1: Write failing tests first

In `tests/api/test_find.py`, update the `test_no_match_returns_404` assertion and add new tests. Replace the `TestFindNoMatches` class and add a new class:

```python
class TestFindNoMatches:
    """Tests for when no persons match the query."""

    @pytest.mark.anyio
    async def test_no_match_returns_404(self, client, valid_api_key, tmp_db):
        resp = await client.post(
            "/v1/find",
            json={"name": "Nonexistent Person"},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["query"]["original"] == "Nonexistent Person"
        assert body["results"] == []
        # message is now messages (list)
        assert "No matching persons found" in body["messages"]

    @pytest.mark.anyio
    async def test_no_match_includes_normalized_query(self, client, valid_api_key, tmp_db):
        resp = await client.post(
            "/v1/find",
            json={"name": "  Bob  Smith  Jr. "},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["query"]["normalized"] == "bob smith jr"


class TestFindInputClassification422:
    """Inputs classified as non-person-names return 422."""

    @pytest.mark.anyio
    async def test_org_suffix_returns_422(self, client, valid_api_key, tmp_db):
        resp = await client.post(
            "/v1/find",
            json={"name": "Acme Corporation"},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_llc_suffix_returns_422(self, client, valid_api_key, tmp_db):
        resp = await client.post(
            "/v1/find",
            json={"name": "Some Business LLC"},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 422
```

Also update `TestFindResponseSchema` — add a test that `messages` is a list:

```python
    @pytest.mark.anyio
    async def test_response_has_messages_list(self, client, valid_api_key, tmp_db):
        """Response should always include messages as a list."""
        resp = await client.post(
            "/v1/find",
            json={"name": "Nobody"},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        body = resp.json()
        assert "messages" in body
        assert isinstance(body["messages"], list)
```

### Step 2: Run tests to confirm they fail

```bash
uv run pytest tests/api/test_find.py -v 2>&1 | head -40
```

Expected: FAIL on `messages` key missing / `search()` type error.

### Step 3: Update `src/api/schemas.py`

Change the `FindResponse` class (only this class changes):

```python
class FindResponse(BaseModel):
    """Response body for POST /v1/find."""

    query: QueryInfo
    results: list[FindResult]
    messages: list[str] = []
```

### Step 4: Update `src/api/routes/v1.py`

Replace the file:

```python
"""Versioned v1 API routes (authenticated)."""

import sqlite3
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from src.api.auth import require_api_key
from src.api.db import get_db
from src.api.schemas import (
    FindRequest,
    FindResponse,
    FindResult,
    HealthResponse,
    MatchedName,
    PersonAttributeSchema,
    PersonNameSchema,
    PersonReadResponse,
    QueryInfo,
)
from src.core.matching import search
from src.core.pipeline import BasicNormalization, StageRegistry, WeightedVariant
from src.core.pipeline.input_classification import InputClassification
from src.core.pipeline.name_parsing import NameParsing
from src.core.pipeline.nickname_expansion import NicknameExpansion
from src.core.pipeline.title_extraction import TitleExtraction
from src.core.reading import read_person

_registry = StageRegistry()
_registry.register("input_classification", InputClassification)
_registry.register("basic_normalization", BasicNormalization)
_registry.register("name_parsing", NameParsing)
_registry.register("nickname_expansion", NicknameExpansion)
_registry.register("title_extraction", TitleExtraction)
_default_pipeline = _registry.build_pipeline([
    "input_classification",
    "basic_normalization",
    "name_parsing",
    "nickname_expansion",
    "title_extraction",
])

v1_router = APIRouter(
    prefix="/v1",
    tags=["v1"],
    dependencies=[Depends(require_api_key)],
)


@v1_router.get("/health", response_model=HealthResponse, tags=["health"])
def v1_health() -> dict:
    """Authenticated health check for the v1 API."""
    return {"status": "ok"}


@v1_router.post("/find", response_model=FindResponse)
def find(
    body: FindRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    """Find persons matching a name query."""
    pipeline_result = _default_pipeline.run(body.name)

    if pipeline_result.is_valid_name is False:
        raise HTTPException(
            status_code=422,
            detail={"messages": pipeline_result.messages},
        )

    normalized = pipeline_result.resolved

    # Deduplicate variants by name, keeping the highest weight.
    # resolved always leads with weight 1.0.
    seen: dict[str, float] = {normalized: 1.0}
    for v in pipeline_result.variants:
        if v.name not in seen or v.weight > seen[v.name]:
            seen[v.name] = v.weight
    unique_variants = [WeightedVariant(name=name, weight=weight) for name, weight in seen.items()]

    query_info = QueryInfo(
        original=body.name,
        normalized=normalized,
        variants=[v.name for v in unique_variants],
    )

    matches = search(conn, unique_variants)
    results = [
        FindResult(
            id=m.person_id,
            certainty=m.certainty,
            matched_name=MatchedName(
                full_name=m.full_name,
                name_type=m.name_type,
            ),
        )
        for m in matches
    ]

    messages = list(pipeline_result.messages)
    if not results:
        messages.append("No matching persons found")

    response = FindResponse(
        query=query_info,
        results=results,
        messages=messages,
    )

    status_code = 200 if results else 404
    return JSONResponse(content=response.model_dump(), status_code=status_code)


@v1_router.get("/read/{person_id}", response_model=PersonReadResponse)
def get_person(
    person_id: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    """Return a full person record by ID."""
    detail = read_person(conn, person_id)
    if detail is None:
        return JSONResponse(
            content={"message": "Person not found"},
            status_code=404,
        )

    names = [PersonNameSchema(**asdict(n)) for n in detail.names]
    attributes = [PersonAttributeSchema(**asdict(a)) for a in detail.attributes]
    response = PersonReadResponse(**asdict(detail.person), names=names, attributes=attributes)

    return JSONResponse(content=response.model_dump(), status_code=200)
```

**Note:** This file imports the four new stage modules. They do not exist yet — the test suite will fail with `ModuleNotFoundError` until Tasks 5–8 are complete. That is expected.

### Step 5: Run the find tests

```bash
uv run pytest tests/api/test_find.py -v 2>&1 | head -30
```

Expected: FAIL with `ModuleNotFoundError` for missing stage modules. That's the next tasks.

### Step 6: Commit what exists so far

```bash
git add src/api/schemas.py src/api/routes/v1.py tests/api/test_find.py
git commit -m "feat: update find endpoint — messages list, 422 gate, WeightedVariant deduplication"
```

---

## Task 4: Add library dependencies

**Files:** `pyproject.toml`, `uv.lock`

### Step 1: Add packages

```bash
uv add nameparser nicknames
```

### Step 2: Verify install

```bash
uv run python -c "from nameparser import HumanName; print(HumanName('Heck, Denny'))"
uv run python -c "from nicknames import NicknameDB; db = NicknameDB(); print(db.nicknames_of('Dennis'))"
```

Expected: both print without errors.

### Step 3: Commit

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add nameparser and nicknames dependencies"
```

---

## Task 5: `InputClassification` stage

**Files:**
- Create: `src/core/pipeline/input_classification.py`
- Create: `tests/core/test_input_classification.py`

### Step 1: Write failing tests

Create `tests/core/test_input_classification.py`:

```python
"""Tests for InputClassification pipeline stage."""

from src.core.pipeline.base import Pipeline, PipelineResult
from src.core.pipeline.input_classification import InputClassification


def _run(name: str) -> PipelineResult:
    return Pipeline(stages=[InputClassification()]).run(name)


class TestOrgSuffixRejection:
    def test_llc_rejected(self):
        result = _run("Acme LLC")
        assert result.is_valid_name is False

    def test_corporation_rejected(self):
        result = _run("Acme Corporation")
        assert result.is_valid_name is False

    def test_inc_rejected(self):
        result = _run("Widgets Inc")
        assert result.is_valid_name is False

    def test_foundation_rejected(self):
        result = _run("Smith Foundation")
        assert result.is_valid_name is False

    def test_case_insensitive_suffix(self):
        result = _run("Acme llc")
        assert result.is_valid_name is False

    def test_message_set_on_rejection(self):
        result = _run("Acme LLC")
        assert any("organization" in m.lower() for m in result.messages)

    def test_person_name_not_rejected(self):
        result = _run("Alice Smith")
        assert result.is_valid_name is not False


class TestParenthesisStripping:
    def test_strips_parenthesized_content(self):
        result = _run("John Smith (DUPLICATE)")
        assert "duplicate" not in result.resolved.lower()
        assert "john smith" in result.resolved.lower()

    def test_message_added_for_stripped_parens(self):
        result = _run("John Smith (DUPLICATE)")
        assert any("parenthesized" in m.lower() or "removed" in m.lower() for m in result.messages)

    def test_empty_after_stripping_sets_invalid(self):
        result = _run("(DUPLICATE)")
        assert result.is_valid_name is False


class TestDigitStripping:
    def test_strips_digits(self):
        result = _run("John Smith 2")
        assert "2" not in result.resolved
        assert "john smith" in result.resolved.lower()

    def test_message_added_for_digits(self):
        result = _run("John Smith 2")
        assert any("digit" in m.lower() for m in result.messages)

    def test_all_digits_sets_invalid(self):
        result = _run("12345")
        assert result.is_valid_name is False


class TestEmailDecoding:
    def test_firstname_lastname_email_decoded(self):
        result = _run("john.smith@example.com")
        assert "john" in result.resolved.lower()
        assert "smith" in result.resolved.lower()

    def test_message_added_for_email(self):
        result = _run("john.smith@example.com")
        assert any("email" in m.lower() for m in result.messages)

    def test_opaque_email_not_decoded(self):
        """jsmith123@example.com has no decodable firstname.lastname pattern."""
        result = _run("jsmith123@example.com")
        # Should not produce a clean name variant; either invalid or unchanged
        assert "jsmith123" not in result.resolved or result.is_valid_name is False

    def test_valid_name_unchanged(self):
        result = _run("Alice Smith")
        assert result.resolved == "Alice Smith"
        assert result.messages == []
        assert result.is_valid_name is None
```

### Step 2: Run tests to confirm they fail

```bash
uv run pytest tests/core/test_input_classification.py -v 2>&1 | head -20
```

Expected: FAIL — module not found.

### Step 3: Implement `src/core/pipeline/input_classification.py`

```python
"""InputClassification pipeline stage — clean and validate name input."""

from __future__ import annotations

import re

from src.core.pipeline.base import PipelineResult, Stage

# Known organization suffixes (matched at end of string, word-boundary-aware, case-insensitive).
_ORG_SUFFIXES = frozenset({
    "llc", "llp", "lp", "inc", "corp", "corporation", "ltd", "limited",
    "foundation", "association", "committee", "pac", "institute", "university",
    "college", "school", "company", "co", "trust", "agency", "bureau",
    "department", "office", "council", "authority", "district",
})

# Matches one or more parenthesized groups anywhere in the string.
_PARENS_RE = re.compile(r"\([^)]*\)")
# Matches digit sequences.
_DIGITS_RE = re.compile(r"\d+")
# Matches firstname.lastname@domain pattern (two dot-separated alpha words before @).
_EMAIL_NAME_RE = re.compile(r"^([a-zA-Z]{2,})\.([a-zA-Z]{2,})@")


def _last_word(s: str) -> str:
    """Return the last whitespace-separated word of *s*, lowercased."""
    parts = s.strip().split()
    return parts[-1].lower() if parts else ""


class InputClassification(Stage):
    """Clean and classify name input before normalization.

    Operates on ``result.original`` to detect patterns that
    ``BasicNormalization`` would obscure (emails, parenthesized content).

    Clean-first strategy:
    - Hard-reject only on known org suffixes.
    - Strip parenthesized content and digits, adding soft messages.
    - Decode ``firstname.lastname@domain`` email patterns.
    - Hard-reject after cleaning if the result is empty.

    Updates ``resolved`` with the cleaned form. Downstream stages
    (starting with ``BasicNormalization``) work from the cleaned string.
    """

    def process(self, result: PipelineResult) -> PipelineResult:
        """Return cleaned PipelineResult, setting is_valid_name when confident."""
        text = result.original
        messages = list(result.messages)

        # --- Email decoding (before org-suffix check to handle email input) ---
        email_match = _EMAIL_NAME_RE.match(text.strip())
        if email_match:
            first, last = email_match.group(1), email_match.group(2)
            text = f"{first.capitalize()} {last.capitalize()}"
            messages.append(f"Name extracted from email address")

        # --- Org suffix hard reject ---
        if _last_word(text) in _ORG_SUFFIXES:
            messages.append(f"Input rejected: appears to be an organization name")
            return PipelineResult(
                original=result.original,
                resolved=result.original,
                variants=list(result.variants),
                messages=messages,
                is_valid_name=False,
            )

        # --- Strip parenthesized content ---
        stripped, n_parens = _PARENS_RE.subn("", text)
        if n_parens:
            messages.append(f"Parenthesized content removed")
            text = stripped.strip()

        # --- Strip digits ---
        stripped, n_digits = _DIGITS_RE.subn("", text)
        if n_digits:
            messages.append(f"Digits removed from input")
            text = stripped.strip()

        # --- Post-cleaning validity check ---
        cleaned = text.strip()
        if not cleaned:
            messages.append("Input is empty after cleaning")
            return PipelineResult(
                original=result.original,
                resolved=result.original,
                variants=list(result.variants),
                messages=messages,
                is_valid_name=False,
            )

        return PipelineResult(
            original=result.original,
            resolved=cleaned,
            variants=list(result.variants),
            messages=messages,
            is_valid_name=result.is_valid_name,
        )
```

### Step 4: Run tests

```bash
uv run pytest tests/core/test_input_classification.py -v
```

Expected: all pass.

### Step 5: Commit

```bash
git add src/core/pipeline/input_classification.py tests/core/test_input_classification.py
git commit -m "feat: add InputClassification stage — org rejection, parens/digit stripping, email decoding"
```

---

## Task 6: `NameParsing` stage

**Files:**
- Create: `src/core/pipeline/name_parsing.py`
- Create: `tests/core/test_name_parsing.py`

### Step 1: Write failing tests

Create `tests/core/test_name_parsing.py`:

```python
"""Tests for NameParsing pipeline stage."""

from src.core.pipeline.base import Pipeline, PipelineResult
from src.core.pipeline.name_parsing import NameParsing


def _run(name: str) -> PipelineResult:
    return Pipeline(stages=[NameParsing()]).run(name)


class TestSurnameFirstDetection:
    def test_surname_first_reordered(self):
        result = _run("Heck, Denny")
        assert result.resolved.lower() == "denny heck"

    def test_message_added_for_reorder(self):
        result = _run("Heck, Denny")
        assert any("surname-first" in m.lower() or "reorder" in m.lower() for m in result.messages)

    def test_normal_order_unchanged(self):
        result = _run("Denny Heck")
        assert result.resolved == "Denny Heck"
        assert result.messages == []


class TestPrefixStripping:
    def test_strips_mr(self):
        result = _run("Mr. John Smith")
        assert "mr" not in result.resolved.lower()
        assert "john smith" in result.resolved.lower()

    def test_strips_dr(self):
        result = _run("Dr. Alice Jones")
        assert "dr" not in result.resolved.lower()

    def test_strips_lieutenant_governor(self):
        result = _run("Lieutenant Governor Heck")
        assert "lieutenant" not in result.resolved.lower()
        assert "governor" not in result.resolved.lower()
        assert "heck" in result.resolved.lower()


class TestSuffixStripping:
    def test_strips_jr(self):
        result = _run("John Smith Jr.")
        assert "jr" not in result.resolved.lower()
        assert "john smith" in result.resolved.lower()

    def test_strips_iii(self):
        result = _run("John Smith III")
        assert "iii" not in result.resolved.lower()


class TestPassthrough:
    def test_passes_through_messages(self):
        stage = NameParsing()
        r = PipelineResult(original="Alice", resolved="Alice", messages=["prior"])
        result = stage.process(r)
        assert "prior" in result.messages

    def test_passes_through_is_valid_name(self):
        stage = NameParsing()
        r = PipelineResult(original="Alice", resolved="Alice", is_valid_name=False)
        result = stage.process(r)
        assert result.is_valid_name is False
```

### Step 2: Run tests to confirm they fail

```bash
uv run pytest tests/core/test_name_parsing.py -v 2>&1 | head -20
```

Expected: FAIL — module not found.

### Step 3: Implement `src/core/pipeline/name_parsing.py`

```python
"""NameParsing pipeline stage — parse name components using nameparser."""

from __future__ import annotations

from nameparser import HumanName

from src.core.pipeline.base import PipelineResult, Stage


class NameParsing(Stage):
    """Parse name structure using the ``nameparser`` library.

    - Detects and corrects surname-first ordering (``"Heck, Denny"``).
    - Strips honorific prefixes (``"Mr."``, ``"Dr."``, ``"Lt. Governor"``).
    - Strips generational suffixes (``"Jr."``, ``"III"``).

    Updates ``resolved`` with the cleaned, reordered name.
    Does not append to ``variants`` — the resolved form retains weight 1.0.
    """

    def process(self, result: PipelineResult) -> PipelineResult:
        """Parse and normalize the resolved name."""
        messages = list(result.messages)
        name = HumanName(result.resolved)

        # Detect surname-first: nameparser sets last when it detects a comma.
        # If the original resolved contained a comma, it was surname-first.
        was_surname_first = "," in result.resolved

        # Reconstruct: first [middle] last (no prefix, no suffix)
        parts = [p for p in [name.first, name.middle, name.last] if p]
        resolved = " ".join(parts) if parts else result.resolved

        if was_surname_first and resolved.lower() != result.resolved.lower():
            messages.append("Surname-first format detected and corrected")

        return PipelineResult(
            original=result.original,
            resolved=resolved,
            variants=list(result.variants),
            messages=messages,
            is_valid_name=result.is_valid_name,
        )
```

### Step 4: Run tests

```bash
uv run pytest tests/core/test_name_parsing.py -v
```

Expected: all pass.

### Step 5: Commit

```bash
git add src/core/pipeline/name_parsing.py tests/core/test_name_parsing.py
git commit -m "feat: add NameParsing stage — surname-first detection, prefix/suffix stripping via nameparser"
```

---

## Task 7: `NicknameExpansion` stage

**Files:**
- Create: `src/core/pipeline/nickname_expansion.py`
- Create: `tests/core/test_nickname_expansion.py`

### Step 1: Write failing tests

Create `tests/core/test_nickname_expansion.py`:

```python
"""Tests for NicknameExpansion pipeline stage."""

from src.core.pipeline.base import Pipeline, PipelineResult
from src.core.pipeline.nickname_expansion import NicknameExpansion

NICKNAME_WEIGHT = 0.85


def _run(name: str) -> PipelineResult:
    return Pipeline(stages=[NicknameExpansion()]).run(name)


class TestNicknameGeneration:
    def test_generates_formal_from_nickname(self):
        result = _run("denny heck")
        names = [v.name for v in result.variants]
        # "denny" should expand to formal forms like "dennis"
        assert any("dennis" in n for n in names)

    def test_generates_nickname_from_formal(self):
        result = _run("dennis heck")
        names = [v.name for v in result.variants]
        assert any("denny" in n for n in names)

    def test_variant_weight_is_085(self):
        result = _run("denny heck")
        for v in result.variants:
            assert v.weight == NICKNAME_WEIGHT

    def test_no_variants_for_unknown_name(self):
        """A given name with no known nicknames should produce no variants."""
        result = _run("xyzabc smith")
        assert result.variants == []

    def test_single_token_input_no_crash(self):
        result = _run("alice")
        # Should not raise; may or may not produce variants
        assert isinstance(result.variants, list)

    def test_resolved_unchanged(self):
        result = _run("denny heck")
        assert result.resolved == "denny heck"

    def test_passes_through_messages(self):
        stage = NicknameExpansion()
        r = PipelineResult(original="Bob", resolved="bob smith", messages=["prior"])
        result = stage.process(r)
        assert "prior" in result.messages

    def test_passes_through_is_valid_name(self):
        stage = NicknameExpansion()
        r = PipelineResult(original="Bob", resolved="bob smith", is_valid_name=False)
        result = stage.process(r)
        assert result.is_valid_name is False
```

### Step 2: Run tests to confirm they fail

```bash
uv run pytest tests/core/test_nickname_expansion.py -v 2>&1 | head -20
```

Expected: FAIL — module not found.

### Step 3: Implement `src/core/pipeline/nickname_expansion.py`

Check the `nicknames` package API before writing — verify the exact method names:

```bash
uv run python -c "from nicknames import NicknameDB; help(NicknameDB)"
```

Then implement:

```python
"""NicknameExpansion pipeline stage — generate given-name variants via nickname lookup."""

from __future__ import annotations

from nicknames import NicknameDB

from src.core.pipeline.base import PipelineResult, Stage, WeightedVariant

_NICKNAME_DB = NicknameDB()
_NICKNAME_WEIGHT = 0.85


class NicknameExpansion(Stage):
    """Generate given-name alternatives using a nickname lookup database.

    Splits the resolved name into tokens, treats the first token as the
    given name, and looks up both nickname and formal-name variants.
    Each variant replaces the first token and is appended to ``variants``
    with weight ``0.85``.

    Requires the resolved name to have at least two tokens (given + surname).
    Single-token inputs are passed through without modification.
    """

    def process(self, result: PipelineResult) -> PipelineResult:
        """Append nickname variants for the given name."""
        parts = result.resolved.split()
        if len(parts) < 2:
            return PipelineResult(
                original=result.original,
                resolved=result.resolved,
                variants=list(result.variants),
                messages=list(result.messages),
                is_valid_name=result.is_valid_name,
            )

        given = parts[0]
        rest = parts[1:]

        # Collect formal and informal equivalents (both directions).
        related: set[str] = set()
        related.update(n.lower() for n in _NICKNAME_DB.nicknames_of(given))
        related.update(n.lower() for n in _NICKNAME_DB.formal_names_of(given))
        related.discard(given.lower())  # exclude the given name itself

        new_variants = [
            WeightedVariant(
                name=" ".join([alt, *rest]),
                weight=_NICKNAME_WEIGHT,
            )
            for alt in sorted(related)
        ]

        return PipelineResult(
            original=result.original,
            resolved=result.resolved,
            variants=[*result.variants, *new_variants],
            messages=list(result.messages),
            is_valid_name=result.is_valid_name,
        )
```

**Note:** If the `nicknames` package uses different method names than `nicknames_of` / `formal_names_of`, adjust accordingly based on the `help()` output from Step 3.

### Step 4: Run tests

```bash
uv run pytest tests/core/test_nickname_expansion.py -v
```

Expected: all pass.

### Step 5: Commit

```bash
git add src/core/pipeline/nickname_expansion.py tests/core/test_nickname_expansion.py
git commit -m "feat: add NicknameExpansion stage — given-name variant generation at weight 0.85"
```

---

## Task 8: `TitleExtraction` stage

**Files:**
- Create: `src/core/pipeline/title_extraction.py`
- Create: `tests/core/test_title_extraction.py`

### Step 1: Write failing tests

Create `tests/core/test_title_extraction.py`:

```python
"""Tests for TitleExtraction pipeline stage."""

from src.core.pipeline.base import Pipeline, PipelineResult
from src.core.pipeline.title_extraction import TitleExtraction

TITLE_WEIGHT = 0.70


def _run(name: str) -> PipelineResult:
    return Pipeline(stages=[TitleExtraction()]).run(name)


class TestTitleDetection:
    def test_senator_prefix_extracts_surname(self):
        result = _run("senator smith")
        names = [v.name for v in result.variants]
        assert "smith" in names

    def test_lieutenant_governor_extracts_surname(self):
        result = _run("lieutenant governor heck")
        names = [v.name for v in result.variants]
        assert "heck" in names

    def test_representative_prefix_extracts_surname(self):
        result = _run("representative jones")
        names = [v.name for v in result.variants]
        assert "jones" in names

    def test_title_variant_has_correct_weight(self):
        result = _run("senator smith")
        for v in result.variants:
            assert v.weight == TITLE_WEIGHT

    def test_no_title_produces_no_variants(self):
        result = _run("alice smith")
        assert result.variants == []

    def test_resolved_unchanged(self):
        result = _run("senator smith")
        assert result.resolved == "senator smith"

    def test_passes_through_messages(self):
        stage = TitleExtraction()
        r = PipelineResult(original="Senator Smith", resolved="senator smith", messages=["prior"])
        result = stage.process(r)
        assert "prior" in result.messages

    def test_passes_through_is_valid_name(self):
        stage = TitleExtraction()
        r = PipelineResult(original="Senator Smith", resolved="senator smith", is_valid_name=False)
        result = stage.process(r)
        assert result.is_valid_name is False
```

### Step 2: Run tests to confirm they fail

```bash
uv run pytest tests/core/test_title_extraction.py -v 2>&1 | head -20
```

Expected: FAIL — module not found.

### Step 3: Implement `src/core/pipeline/title_extraction.py`

```python
"""TitleExtraction pipeline stage — extract surname from occupational title strings."""

from __future__ import annotations

from src.core.pipeline.base import PipelineResult, Stage, WeightedVariant

# Ordered list of multi-word title prefixes (longer first to match greedily).
# All entries are lowercase; matched against the lowercased resolved name.
_TITLE_PREFIXES: list[tuple[str, ...]] = [
    ("lieutenant", "governor"),
    ("vice", "president"),
    ("attorney", "general"),
    ("secretary", "of", "state"),
    ("lieutenant",),
    ("governor",),
    ("senator",),
    ("representative",),
    ("congressman",),
    ("congresswoman",),
    ("delegate",),
    ("mayor",),
    ("president",),
    ("commissioner",),
    ("councilman",),
    ("councilwoman",),
    ("councilmember",),
    ("assemblyman",),
    ("assemblywoman",),
    ("assemblymember",),
    ("treasurer",),
    ("comptroller",),
]

_TITLE_WEIGHT = 0.70


class TitleExtraction(Stage):
    """Extract a surname variant from occupational title prefixes.

    Detects known title words at the start of the resolved name and
    appends the remaining token(s) as a ``WeightedVariant`` at weight
    ``0.70``. The resolved form is left unchanged.

    Only single trailing tokens are extracted (e.g. ``"senator smith"``
    → ``"smith"``). Multi-token remainders are not appended to avoid
    false positives.
    """

    def process(self, result: PipelineResult) -> PipelineResult:
        """Append a surname variant if the resolved name starts with a title."""
        tokens = result.resolved.lower().split()
        remainder = self._strip_title(tokens)

        variants = list(result.variants)
        if remainder is not None and len(remainder) == 1:
            variants.append(WeightedVariant(name=remainder[0], weight=_TITLE_WEIGHT))

        return PipelineResult(
            original=result.original,
            resolved=result.resolved,
            variants=variants,
            messages=list(result.messages),
            is_valid_name=result.is_valid_name,
        )

    def _strip_title(self, tokens: list[str]) -> list[str] | None:
        """Return the token list after stripping a leading title, or None if no title found."""
        for prefix in _TITLE_PREFIXES:
            n = len(prefix)
            if tokens[:n] == list(prefix) and len(tokens) > n:
                return tokens[n:]
        return None
```

### Step 4: Run tests

```bash
uv run pytest tests/core/test_title_extraction.py -v
```

Expected: all pass.

### Step 5: Commit

```bash
git add src/core/pipeline/title_extraction.py tests/core/test_title_extraction.py
git commit -m "feat: add TitleExtraction stage — surname extraction from occupational title prefixes at weight 0.70"
```

---

## Task 9: Full suite verification

### Step 1: Run the complete test suite

```bash
uv run pytest --no-cov -q
```

Expected: all 745+ tests pass (plus new tests from Tasks 1–8).

### Step 2: Run lint

```bash
uv run ruff check . && uv run ruff format . --check
```

Fix any issues before proceeding.

### Step 3: Integration smoke test

```bash
uv run pytest tests/api/test_find.py -v
```

Verify all find endpoint tests pass, including the new `TestFindInputClassification422` class.

### Step 4: Final commit if lint fixes were needed

```bash
git add -u
git commit -m "chore: fix lint issues"
```

---

## Implementation Notes

- **Stage order matters:** `InputClassification` must run before `BasicNormalization` so its cleaned output (e.g. extracted email names in proper case) is subsequently lowercased. This differs from the design doc's stated order but is architecturally required.
- **`nicknames` API:** Verify exact method names (`nicknames_of`, `formal_names_of`) against the installed version before implementing Task 7.
- **`nameparser` prefix stripping:** The library's prefix/title handling is vocabulary-driven. For titles not in its vocabulary (e.g. "Assemblymember"), `TitleExtraction` handles the gap.
- **Matching layer imports:** `matching.py` now imports from `src.core.pipeline.base`. This creates a dependency from `core.matching` → `core.pipeline`. Acceptable given they are both pure domain modules with no API-layer imports.
