# Recipe: Git Hooks

This boilerplate ships two git hooks under `.githooks/`:

- **`pre-commit`** — auto-regenerates artefacts that should never go stale (e.g. OpenAPI spec when API files change).
- **`pre-push`** — runs lint + sync checks before a push reaches CI. Saves GitHub Actions minutes (~1.6–2k/month on a busy project — measured on a real downstream project under DEAL-2284).

Both hooks are **non-blocking when dependencies are missing**: they exit `0` with a notice instead of erroring. This is critical for adoption — a hook that hard-errors when a fresh clone lacks `ruff` will be disabled (or `--no-verify` will become the default).

## One-time setup

```bash
git config --local core.hooksPath .githooks
```

That's it. Works across worktrees — git resolves the relative `.githooks` path from each worktree's root, and every checkout has `.githooks/`.

`bin/vibe doctor` warns if `core.hooksPath` isn't set so you'll be reminded if you forget.

## What each hook does

### `.githooks/pre-commit`

Path-gated: only fires when files in `api/` or `schemas/pydantic/` are staged (override the regex via `.vibe/config.json` `git_hooks.pre_commit.api_paths_regex`). When triggered:

1. Detects `scripts/export_openapi.py` (FastAPI convention) and runs it via `uv run python` (or system `python3` as fallback)
2. Re-stages `docs/api/openapi.json` if the regenerated content differs
3. Skips with a notice if FastAPI isn't installed (e.g. fresh clone before `uv sync`)
4. Runs every executable in `.githooks/pre-commit.d/*.sh` for project-specific extensions

Non-blocking throughout — failures print to stderr and exit 0.

### `.githooks/pre-push`

Runs in this order, aggregating failures:

1. `ruff check . --output-format=concise`
2. `ruff format . --check --diff --quiet`
3. `mypy lib/vibe/` (only if mypy is installed and `lib/vibe/` exists)
4. `pytest --tb=short -q` (opt-in via `VIBE_PRE_PUSH_PYTEST=1` — slow by default)
5. Every executable in `.githooks/pre-push.d/*.sh` (project-specific)

If any check fails, the push is blocked with a summary and the bypass instruction (`git push --no-verify`). If `ruff` or `python` isn't available at all, the hook exits 0 with a notice — fresh clones don't see push failures because of missing tooling.

## Project-specific extensions: `.githooks/<hook>.d/*.sh`

Drop executable scripts into `.githooks/pre-commit.d/` or `.githooks/pre-push.d/`. They run after the standard checks. Each script should:

- Be marked executable (`chmod +x`)
- Exit `0` on success, non-zero on failure
- Print its own status to stdout/stderr — the hook just runs it; it doesn't wrap output

Example — a downstream project that wants to warn when their dbt tile macro changes:

```bash
# .githooks/pre-push.d/tile-macro-warning.sh
#!/usr/bin/env bash
set -uo pipefail

TILE_MACRO="transforms/macros/create_tile_filtered_parcels_function.sql"

if git diff --name-only origin/main...HEAD 2>/dev/null \
     | grep -qF "$TILE_MACRO"; then
  echo ""
  echo "[pre-push] ⚠️  Tile macro changed: $TILE_MACRO"
  echo "[pre-push]    The PostgreSQL function is recreated via a dbt post-hook."
  echo "[pre-push]    After this PR merges, create a rematerialize ticket so"
  echo "[pre-push]    the new function definition goes live in production."
  echo ""
fi

exit 0  # warning only, never block
```

This is exactly the pattern that's project-specific enough to NOT belong in the shipped hook but is still valuable to standardise via the drop-in.

## Why "non-blocking" matters

A single bad experience teaches developers to disable hooks. The fastest path to "everyone runs `git push --no-verify` now" is:

1. Hook hard-errors when `ruff` is missing
2. Developer can't push their hotfix
3. They Google, find `--no-verify`, alias it
4. Hook is now bypassed permanently

Both shipped hooks treat missing dependencies as a **skip**, not a failure. Real failures (lint errors in present code) still block the push — but that's the desired outcome.

If you find yourself reaching for `--no-verify` repeatedly, that's a signal the hook is wrong, not the developer. File a ticket; don't normalise the bypass.

## Worktree resolution

`git config --local core.hooksPath .githooks` sets the path at the *repo* level (`.git/config`). Worktrees inherit this setting (they share the same repo metadata). When git triggers a hook in a worktree, it resolves `.githooks` relative to that worktree's working directory — so as long as every checkout has the `.githooks/` directory, hooks work everywhere.

This was a non-obvious property of git that took some experimentation to confirm. If you ever clone the repo and find hooks aren't running, check `git config --local core.hooksPath` in that worktree first.

## Bypass procedure

Real emergencies happen. To bypass:

```bash
git push --no-verify
```

Use sparingly. If `bin/vibe doctor` flags a high `--no-verify` rate (future enhancement), investigate which check is triggering avoidance.

## Economics — DEAL-2284

Measured on a real downstream project after introducing `.githooks/pre-push`:

- **~1,600–2,000 GitHub Actions minutes saved per month**
- ~30+ pre-push failures caught per week that would otherwise have triggered full CI runs
- Most-caught pattern: ruff format diff (autoformatter run forgotten before commit)

The economics work because:
1. Local lint runs in <30s on warm caches; equivalent CI job takes 1-3 min including queue + checkout + dep install
2. Push failures consume zero CI minutes; they fail before reaching GitHub
3. Faster feedback loop — devs see ruff failure in 5s, not 5 min

For a team of 4 active developers pushing ~10 times per week each, that's ~1,600 saved CI minutes monthly assuming a 50% catch rate. Most teams measure higher.

## Cross-references

- `agent_instructions/CLI.md` § CLI Conventions — the broader doctrine that frames CLI / hook design
- `bin/ci-local` — runs the same checks the pre-push hook does, plus a few more (frontend tests, gitleaks). Use it interactively when you want a fuller check than just pre-push.
- Anti-patterns in CLAUDE.md — "Don't push CLI changes without smoke-testing every subcommand" pairs with this hook for higher confidence.
