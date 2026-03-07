#!/usr/bin/env bash
# pre-ship.sh
# Runs lint and tests. Exits non-zero on any failure.
# Detects the git project root automatically; safe to invoke from any directory.
#
# Usage: bash skills/shipping-work-claude/scripts/pre-ship.sh [--help]
set -euo pipefail

if [[ "${1:-}" == "--help" ]]; then
  echo "Usage: bash skills/shipping-work-claude/scripts/pre-ship.sh"
  echo ""
  echo "Runs ruff lint and pytest. Exits non-zero on any failure."
  echo "Must pass before committing or pushing."
  echo ""
  echo "Exit codes:"
  echo "  0  All checks passed"
  echo "  1  Lint or test failure"
  exit 0
fi

PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$PROJECT_ROOT"

echo "=== Lint (ruff) ==="
uv run ruff check .

echo ""
echo "=== Tests ==="
# Determine if we need to run the test suite:
# skip if the working tree is clean AND we already stamped this exact commit.
CURRENT_SHA=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
STAMP_FILE="/tmp/pv-tests-clean-${CURRENT_SHA}"
# Only track staged/unstaged changes to tracked files; ignore untracked files.
WORKING_TREE_DIRTY=$(git status --porcelain 2>/dev/null | grep -v '^??' || true)

if [[ -f "$STAMP_FILE" && -z "$WORKING_TREE_DIRTY" ]]; then
  echo "Test suite already passed for commit ${CURRENT_SHA:0:7} with a clean working tree — skipping."
else
  # Always exclude integration tests: they hit live external services and are
  # unsuitable for routine pre-ship validation (slow, flaky, network-dependent).
  # Run integration tests explicitly with: uv run pytest -m integration
  uv run pytest --no-cov -x -m "not integration"
  # Stamp success only when working tree is clean (dirty trees can't be cached).
  if [[ -z "$WORKING_TREE_DIRTY" ]]; then
    touch "$STAMP_FILE"
  fi
fi

echo ""
echo "Pre-ship checks passed."
