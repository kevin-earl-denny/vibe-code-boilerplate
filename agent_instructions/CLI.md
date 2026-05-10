# CLI Conventions

The `bin/*` wrappers (and `npm run *` scripts) are the primary interface for agent-driven work. As the CLI surface grows, three patterns are foundational. Following them keeps every CLI reliable, debuggable, and composable; ignoring them produces silent failures, opaque errors, and DX papercuts that compound across sessions.

These rules apply to **CLIs we author** (`bin/vibe`, `bin/ticket`, `bin/secrets`, plus any new wrappers). Third-party CLIs (`gh`, `fly`, `vercel`, `psql`) are out of scope — we don't own them and can't fix them, though we should still document their gotchas in agent memory.

---

## Rule 1 — Reliability: capture-or-file every CLI error

Every CLI invocation should succeed. When one errors, classify and act:

- **Agent's fault** (wrong flag, missed prerequisite, misread output) → write a feedback memory entry (e.g. `feedback_cli_<cli>_<topic>.md`) so the same mistake doesn't recur in future sessions.
- **CLI's fault** (silent failure, confusing error, missing flag, broken default, parser drift, wrong exit code, undocumented behaviour) → file a Linear ticket marked **Urgent** and post to your project's CLI/agent-DX discussion channel with repro steps + ticket link.

The bar for "Urgent" is intentionally low: any DX papercut counts, not just blockers. The cost of agent friction compounds across sessions, so each papercut is worth fixing fast.

**Why this rule exists.** Without explicit classification, CLI errors get silently retried, ignored, or worked-around. Each silent retry trains the agent to tolerate broken tools instead of fixing them. Forcing a write-or-file decision creates a paper trail that turns one-off frustrations into systemic improvement.

**Worked example — `bin/logs` parser drift.** Axiom changed its tabular response shape from row-major (`tables[0].rows`) to column-major (`tables[0].columns`). The bash version of `bin/logs` parsed the old shape, so every query silently returned `"No results."` for weeks. Hours of agent time were spent debugging "why is the dataset empty?" before the issue was traced to the parser. The fix: rewrite the CLI in Python, add response-shape validation, and exit `2` (not `0` with empty output) on shape drift. That single incident produced this entire doctrine.

---

## Rule 2 — Pre-PR testing: smoke-test every subcommand of the modified CLI

Before opening a PR that touches CLI code, **live-test every subcommand** of the modified CLI(s) — not just the ones directly changed. Shared modules, argparse changes, config loading, and output formatters routinely break adjacent subcommands.

Document the test matrix in the PR description, one line per subcommand:

```
✅ bin/cli sub-a --flag value   # passes
✅ bin/cli sub-b                # passes
⏸️ bin/cli sub-c                # blocked on PROJ-NNNN (missing endpoint)
❌ bin/cli sub-d --foo          # fails — see PROJ-MMMM
```

If a subcommand can't be tested due to an unfulfilled dependency:

1. File a Linear ticket: `<CLI>: test + fix <command>` (group commands sharing the dependency).
2. Set the new ticket as **blocked by** the dependency ticket.
3. Note it as ⏸️ in the PR matrix; ship the PR if the untestable command is unrelated to the change, hold it if it's the hot path.

### No CLI tests in GitHub Actions

Local live runs are the source of truth. CI tests of CLIs tend to mock the world and pass while the real command is broken — exactly the failure mode that produced the parser-drift incident.

- **Prefer live tests** over mocked tests for new CLI functionality. Hit real APIs, real datasets, real third-party services. The slowness is the price of catching real regressions.
- Test files (snapshots, fixtures) are for **regression detection**, not primary verification.
- ✅ in the PR matrix means a successful **live local run**, not just a passing unit test.

**Why this rule exists.** A CLI's job is to talk to a real external system. Mocked tests verify your code's *internal* behaviour but not the *integration*, which is exactly where CLIs go wrong. The parser-drift incident is the canonical example: a comprehensive mocked test suite passed for months while the real command silently returned empty results.

---

## Rule 3 — Maximalist + documented

When building or extending a CLI, default to **maximalist** scope: expose every reasonably useful API capability or data surface as a subcommand, not just the minimum the immediate task requires. The bar for inclusion is low — each new subcommand becomes a stable, documented affordance the agent can rely on indefinitely, and the cost of building five subcommands now is far less than the compounded friction of needing them later across many sessions.

### Documentation is part of the deliverable

Not a follow-up. The same PR that ships a new subcommand must include:

- **Inline `--help`** for the CLI and every subcommand, with flags + at least one example per subcommand.
- A dedicated **`docs/operations/<cli>-cli-reference.md`** enumerating subcommands, flags, output formats, and exit codes. (Use [`recipes/cli/cli-reference-template.md`](../recipes/cli/cli-reference-template.md) as a starting point.)
- A row (or section) in `CLAUDE.md` § Skills & CLI Reference table.
- A `reference_<cli>.md` entry in agent memory if the CLI has agent-relevant gotchas.

### Output formats

Support three output modes:

- **`pretty`** — aligned tables / human-readable formatting. Default when stdout is a TTY.
- **`jsonl`** — one JSON object per line. Default when stdout is piped (so `bin/foo | jq …` works without a flag).
- **`--format pretty|json|jsonl|raw|csv|auto`** — explicit override. Agents need machine-parseable output; this is non-optional.

### Exit codes

Standardise on this scheme:

| Code | Meaning |
|---|---|
| `0` | success — including genuinely-empty result sets |
| `1` | expected error — bad args, missing token, file not found, 4xx response, validation failure |
| `2` | unexpected drift — parser drift, schema mismatch, response-shape change. **Treat as an incident, not a flake.** |
| `3` | network / API error — timeout, DNS failure, 5xx response, JSON decode failure |

Exit code `2` is the most important — it's the difference between "loudly fail when the world changed" and "silently lie." The parser-drift incident is the model: when in doubt, prefer `2` over `0` with empty output.

**Fail loud, not silent.** A genuinely-empty result set is `0`; an empty result set caused by a parser bug is `2`. Detect drift by validating the response structure (column names, row counts where known, type sanity checks) before parsing, and emit a structured error message naming exactly which expectation failed.

**Why this rule exists.** Thin wrappers ("just enough to do the immediate task") force the next agent to drop down to raw API calls when the CLI doesn't cover their case — wasting context, accumulating duplicate ad-hoc tooling, and never paying down the documentation debt. Maximalism amortises the build cost over many future sessions.

---

## Anti-patterns to avoid

These four anti-patterns are codified in `CORE.md` § Anti-Patterns. Re-stated here for reference:

- **Don't ship a CLI PR without smoke-testing every command of the modified CLI.** Live local runs only; document the test matrix (✅/❌/⏸️) in the PR description.
- **Don't add CLI tests to GitHub Actions.** Local live tests are the source of truth. CI tests of CLIs tend to mock the world and pass while the real command is broken.
- **Don't ship thin CLI wrappers.** Default to maximalist surface area + thorough docs. Inline `--help` + a `docs/operations/<cli>-cli-reference.md` + a row in CLAUDE.md table all land in the same PR.
- **Don't silently retry or ignore CLI errors.** Classify every error: agent-fault → memory file; CLI-fault → Urgent ticket + DX-channel post.

---

## Implementing a new CLI — checklist

When creating `bin/<new-cli>`:

1. **Bash wrapper at `bin/<new-cli>`**, ~30 lines: ensure `.vibe/.venv` exists, activate it, exec `python -m lib.vibe.cli.<new-cli> "$@"`. Mirror the pattern in `bin/secrets`, `bin/ticket`.
2. **Implementation at `lib/vibe/cli/<new_cli>.py`**, an `argparse`-based dispatcher with one function per subcommand. Subclass `CLIError`, `ParserDriftError`, `NetworkError` for the exit-code scheme.
3. **Inline `--help`** for the top level + each subcommand, with at least one example per subcommand.
4. **Output formats** — pretty (TTY), jsonl (pipe), `--format` override.
5. **Exit codes** — 0/1/2/3 per the table above. Validate response shapes before parsing; emit `2` on drift.
6. **`docs/operations/<new-cli>-cli-reference.md`** — copy [`recipes/cli/cli-reference-template.md`](../recipes/cli/cli-reference-template.md), fill in subcommand catalogue, flags, output formats, exit codes, common patterns, token rotation if applicable.
7. **CLAUDE.md template** — add a row to the § Skills & CLI Reference table.
8. **PR description** — include the smoke-test matrix (✅/⏸️/❌) for every subcommand, not just changed ones.

Run `bin/ci-local` before pushing — it catches lint, format, and version-sync issues that would otherwise cost a CI cycle.

---

## Cross-references

- `recipes/cli/cli-conventions.md` — long-form recipe with the parser-drift post-mortem and worked examples
- `recipes/cli/cli-reference-template.md` — template for `docs/operations/<cli>-cli-reference.md`
- `bin/ci-local` — local CI mirror; runs all locally-runnable checks in one command
- `CORE.md` § Anti-Patterns — the four CLI anti-patterns
