---
name: shipping-work-claude
description: "Finalizes work by ensuring everything is committed, pushed to the remote, and reflected on GitHub: closes issues, posts summary comments, and presents a completion table. Use when the user says 'ship it', 'push GH', 'close GH', or 'wrap up'."
compatibility: Designed for Claude. Requires git and gh CLI. Python project using uv, ruff, pytest, Django, systemd.
metadata:
  author: gregoryfoster
  version: "1.0"
  triggers: ship it, push GH, close GH, wrap up
  overrides: shipping-work-claude
  override-reason: "Concrete test/lint commands (uv run pytest --no-cov, uv run ruff check); project commit convention (#n [type]: desc); systemd service restart step after push"
---

# Shipping Work — person-validator

Finalizes work: lint, tests, clean commit, push, GitHub issue comments and closure.

## Scope detection

Determine which GitHub issue(s) to close (priority order):
1. **Explicit scope** — user specifies issue number(s) (e.g., `wrap up #19 #20`)
2. **Conversation context** — issues referenced in recent commit messages or discussion
3. **Ask** — if ambiguous, confirm before closing anything

## Procedure

### Step 1 — Lint and test

```bash
bash skills/shipping-work-claude/scripts/pre-ship.sh
```

Do not proceed if lint or tests fail.

**Integration tests are always excluded** from `pre-ship.sh`. They hit live
external services (Wikidata, Wikipedia) and are unsuitable for routine
validation — slow, flaky, and network-dependent. Run them explicitly with:
```bash
uv run pytest -m integration
```

**Smart skip:** If the working tree is clean and the test suite already passed
for the current commit (stamped at `/tmp/pv-tests-clean-<sha>`), the test run
is skipped. This prevents redundant runs when shipping immediately after a
full test pass during development.

### Step 2 — Ensure a clean working tree

```bash
bash skills/shipping-work-claude/scripts/check-status.sh
```

If uncommitted changes exist, commit them using this project's convention:
```
#<number> [type]: <description>       # with GH issue
[type]: <description>                 # without GH issue
```
Multiple issues: `#19, #20 [type]: <description>`  
Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

### Step 3 — Ensure on main

If on a feature branch, merge to `main` first. Then continue.

### Step 4 — Push

```bash
bash skills/shipping-work-claude/scripts/push.sh
```

### Step 5 — Comment on GitHub issues

For each issue in scope:

```bash
bash skills/shipping-work-claude/scripts/comment-issue.sh <number> "<summary>"
```

Comment must include:
- What was implemented (2–4 bullets)
- Key commit SHAs or commit range
- Any follow-up items or known limitations

### Step 6 — Close GitHub issues

```bash
bash skills/shipping-work-claude/scripts/close-issue.sh <number>
```

Never close an issue that wasn't fully implemented — ask first if uncertain.

### Step 7 — Restart services if needed

If any files under `src/api/` or `src/core/` changed, restart the API service.
If any files under `src/web/` changed, restart the web service.

```bash
sudo systemctl restart person-validator-api   # if API/core files changed
sudo systemctl restart person-validator-web   # if web files changed
```

Attempt the restart automatically. If it fails (e.g. permission error), prompt the user:
> "Service restart failed — please run: `sudo systemctl restart person-validator-api` (or -web)"

If no service-relevant files changed, skip this step silently.

### Step 8 — Report

Present a summary table:

| Issue | Title | Status | Comment |
|---|---|---|---|
| #19 | ... | ✅ Closed | Summary posted |
