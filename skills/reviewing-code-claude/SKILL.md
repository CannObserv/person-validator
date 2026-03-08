---
name: reviewing-code-claude
description: Performs a structured code and documentation review using a severity-tiered findings format. Use when the user says "CR", "code review", or "perform a review". Produces a numbered findings report, waits for terse directives (fix/stet/GH), then implements and commits approved changes.
compatibility: Designed for Claude. Requires git and gh CLI. Python project using Django, FastAPI, Pydantic, uv, ruff, pytest.
metadata:
  author: gregoryfoster
  version: "1.1"
  triggers: CR, code review, perform a review
  overrides: reviewing-code-claude
  override-reason: Django/FastAPI-specific review dimensions; ruff lint check; TDD red/green discipline; pipeline stage contracts; migration safety; JSON logging convention; Iron Law + rationalization-prevention table; Phase 3.5 verification gate
---

# Code & Documentation Review — person-validator

A systematic review workflow for this Django + FastAPI/Pydantic/uv project. Produces a numbered findings report, waits for directives, then implements approved changes.

## The Iron Law

```
NO FINDINGS REPORT WITHOUT RUNNING THE TEST SUITE FIRST
NO CHANGES WITHOUT A FINDINGS REPORT AND EXPLICIT USER DIRECTIVES
```

If you haven't run `gather-context.sh` and confirmed tests pass, you have not completed Phase 1.
If the user hasn't responded with directives, you cannot implement anything.

## Rationalization prevention

| Thought | Reality |
|---|---|
| "It's a small change, no need for a full review" | Size doesn't determine risk. Run the review. |
| "I just implemented this, I know it's correct" | Familiarity bias. Fresh pass finds what implementation blindness missed. |
| "Tests are passing, that's the review" | Tests verify behavior, not convention compliance, migration safety, or docs. |
| "The user seems in a hurry" | A fast broken change is slower than a thorough correct one. |
| "I'll fix things as I find them" | Phase 4 exists. Present first, implement after directives. |
| "This file wasn't in the diff" | Related files need review too. Check call sites, tests, AGENTS.md. |

## Scope detection

Determine what to review (priority order):
1. **Explicit scope** — files, branch, commit range, or issue number specified by the user
2. **Conversation context** — changes implemented in this conversation
3. **Uncommitted work** — `git diff` and `git diff --staged`
4. **Ask** — if scope is ambiguous, ask before proceeding

## Procedure

### Phase 1 — Gather context

```bash
bash skills/reviewing-code-claude/scripts/gather-context.sh
```

Also:
- Read AGENTS.md conventions relevant to the changed files
- Identify all files touched and their roles in the architecture
- Check the live app if template/UI or API changes are involved (browser screenshot)

**Do not run the test suite during a review.** The code review phase is
read-only analysis. Tests run at ship time via `pre-ship.sh`, which skips
redundantly if the suite already passed for the current commit. If you need
to verify a specific failing behaviour, run only the relevant test file:
```bash
uv run pytest tests/path/to/test_file.py --no-cov -m "not integration"
```

### Phase 2 — Analyze

Evaluate against these dimensions:

- **Correctness** — bugs, logic errors, edge cases, off-by-ones
- **TDD discipline** — does every production change have a corresponding test? Is the red commit present before the green commit?
- **API contract** — Pydantic model changes; field names, types, and validation; breaking vs. non-breaking per AGENTS.md versioning strategy
- **Django ORM safety** — N+1 queries, missing `select_related`/`prefetch_related`, `QuerySet.update()` must include `updated_at=timezone.now()`
- **Migration safety** — new migrations present for model changes; migrations are reversible; no data-loss operations without explicit confirmation
- **Pipeline stage contracts** — stages only update `resolved` and `variants`; never mutate incoming result or touch `original`; normalisation stages do not self-append to variants
- **Auth blast-radius** — any change near `src/api/auth.py`, API key handling, or `keys/` app
- **Convention compliance** — AGENTS.md patterns: JSON logging via `get_logger(__name__)`, `configure_logging()` only at entry points, ISO 8601 timestamps, UTC-only datetimes, `timezone.now()` not `datetime.now()`
- **Documentation** — do AGENTS.md, README.md, and code comments reflect the changes? Schema table updated if models changed?
- **Robustness** — error handling, graceful degradation, idempotency, Pydantic `Field` constraints
- **Test coverage** — new logic needs tests; coverage should not regress

### Phase 3 — Verify before reporting

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION
```

- Re-run tests if any implementation happened in this conversation
- If tests fail: report the failure as a 🔴 finding regardless of cause
- Do NOT claim "tests pass" unless you have output from this session confirming it

### Phase 4 — Present findings

Title: `## Code & Documentation Review — [scope]`

1. **What's solid** — genuine positives, not filler
2. **Numbered findings** — sequential across ALL severity groups, never reset between them
   - Top-level: `1.`, `2.`, `3.` — Sub-items: `2a.`, `2b.`
   - Each finding: **What** (file:line) · **Why it matters** · **Suggested fix** (code snippet when useful)
   - Groups: 🔴 Bugs → 🟡 Issues to fix → 💭 Minor/observations
3. **Summary** — 1–2 sentences on overall assessment and top priorities

### Phase 5 — Wait for feedback

**Stop. Do not make changes until the user responds.**

Accepted directives (reference by item number):

| Directive | Meaning |
|---|---|
| `1: fix` | Implement the suggested fix |
| `3: stet` | Leave as-is |
| `5: fix, but use X approach` | Fix with user's preferred approach |
| `2: document as TODO` | Add a code comment or AGENTS.md note |
| `7: investigate further` | Gather more information first |
| `10: GH` | Create or update a GitHub issue |

After directives, implement all requested changes. Before committing, run the test suite and confirm it passes — report any failures before committing. Then commit and present a summary table:

| Item | Action | Result |
|---|---|---|
| 1 | Fixed | `src/api/routes/v1.py:42 — added bounds check` |
| 3 | Stet | — |

## Second review rounds

Continue numbering from where the previous round ended. Never reset.

## Documentation sweep

Flag missing documentation updates as numbered findings when changes affect:

- **Database schema** → AGENTS.md schema section
- **New files or public APIs** → AGENTS.md Key Files table and relevant sections
- **User-facing behaviour** → README.md
- **Deployment or CLI** → AGENTS.md Common Tasks

## Parameterized invocation

Triggers may include scope inline — e.g., `CR #14`, `code review src/api/routes/v1.py`. Apply the appended context as the explicit scope (step 1 of scope detection).
