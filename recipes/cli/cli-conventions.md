# Recipe: CLI Conventions

This recipe explains the doctrine that governs every `bin/*` wrapper in this boilerplate (and any project that adopts these conventions). It expands on `agent_instructions/CLI.md` with a worked post-mortem and side-by-side examples.

## TL;DR

Three rules:

1. **Capture or file every CLI error.** Agent's fault → memory entry. CLI's fault → Urgent ticket + DX-channel post.
2. **Smoke-test every subcommand before opening a PR.** Document the matrix (✅/❌/⏸️). No CLI tests in GHA.
3. **Maximalist + documented.** Ship every useful subcommand at once, with `--help`, a `docs/operations/<cli>-cli-reference.md`, and a row in CLAUDE.md. Output formats: pretty / jsonl / `--format`. Exit codes: `0`/`1`/`2`/`3` per the standard scheme.

## Why these rules exist — the parser-drift post-mortem

The motivating incident: a Python service shipped structured logs to a query-as-a-service backend (Axiom). A bash-based `bin/logs` CLI parsed the API response. The API's response format was *roughly* JSON, but with a tabular wrapper:

```json
{
  "tables": [{
    "columns": [
      {"name": "_time", "values": ["2026-04-01T..."]},
      {"name": "msg", "values": ["request"]}
    ]
  }]
}
```

The bash CLI parsed it as if it were row-major:

```json
{
  "tables": [{
    "rows": [
      {"_time": "2026-04-01T...", "msg": "request"}
    ]
  }]
}
```

Both shapes are valid JSON. Both shapes have non-empty `tables[0]`. The bash parser, looking for `tables[0].rows` (which doesn't exist in the column-major format), returned `[]` — and printed `"No results."` to stdout, exit code `0`.

For weeks, every log query silently returned no results. Agents spent hours wondering whether logs were even shipping. Eventually someone noticed the same query worked in the Axiom UI but not via the CLI, and the parser bug was found.

### What went wrong

Three failures compounded:

1. **No response-shape validation.** The CLI assumed a structure without checking. A two-line guard (`assert "rows" in tables[0], "expected row-major shape"`) would have caught the drift the moment Axiom changed the format.
2. **Empty results returned exit `0`.** This was correct *if* the dataset was actually empty, but indistinguishable from a parser bug. The agent couldn't tell whether to keep investigating or trust the empty result.
3. **No CLI smoke-tests against the real API.** Mocked tests verified the bash parser worked on synthetic row-major fixtures. The real API was column-major; mocks didn't catch the divergence.

### The fix that codified the rules

The CLI was rewritten in Python with three changes:

1. **Response-shape validation.** Before extracting rows, validate that `tables[0]` has `columns` (the current shape) and that the column count matches expectations. If not → raise `ParserDriftError`.
2. **Exit code 2 on parser drift.** `ParserDriftError` returns exit `2`, not `0`. This is loud; CI / cron / agent loops know to treat exit `2` as "the API changed, investigate now" rather than "no results, move on."
3. **Live local smoke tests.** Every subcommand is run against real Axiom before opening a PR. The PR description includes a matrix of ✅/❌/⏸️ per subcommand.

Each fix became a rule. Each rule is a contract that any future CLI in this boilerplate inherits.

## Rule 1 in practice — capturing CLI errors

Two paths, both with low friction:

### Path A: agent's fault → memory entry

The agent ran the wrong flag, misread output, or skipped a prerequisite. Write a feedback memory file:

```
feedback_cli_logs_default_window.md

When using bin/logs to look for ETL/Inngest activity, the default --since 1h is
too short — most ETL functions run daily-to-weekly. Bump --since to 7d or 14d
when looking for ingest activity. (Saw this twice; --since defaults make sense
for HTTP debugging but not for cron-triggered jobs.)
```

Memory files live in your agent's memory directory (`~/.claude/projects/<project>/memory/` or equivalent). They're surfaced automatically in future sessions when the topic is relevant.

### Path B: CLI's fault → Urgent ticket + DX-channel post

The CLI returned the wrong exit code, the help text was wrong, the default was broken, the response parser silently dropped data. File a Linear ticket marked **Urgent** and post to your CLI/DX discussion channel:

```
Title:    bin/logs: --until flag silently ignored after --since
Labels:   Bug, Urgent, Backend, Agent DX
Body:
  Repro:
    bin/logs query "level == 'error'" --since 24h --until 12h
  Expected: rows from 12-24h ago
  Actual:   rows from last 1h (default), --until is ignored
  Source:   lib/vibe/cli/logs.py:queries.py:127 — only --since is forwarded

  This blocks investigation of any incident older than ~1h via the CLI.
  Workaround: use bin/logs apl directly with explicit time bounds.
```

Slack post:
```
🐛 bin/logs --until silently ignored — repro + ticket
PROJ-NNNN | Bug | Urgent | Backend
Files <PROJ-NNNN> for the --until flag being silently dropped. Workaround
documented in the ticket. Hits anyone trying to investigate >1h-old incidents.
```

The bar for "Urgent" is intentionally low. Any DX papercut qualifies. The cost of agent friction compounds across sessions; each papercut fixed quickly is leverage for every future session.

### Third-party CLIs are out of scope

`gh`, `fly`, `vercel`, `psql`, `aws`, `kubectl` — when these misbehave, write a memory entry but **don't file a ticket**. We don't own them and can't fix them. Memory captures the gotcha; that's enough.

The exception is wrappers we author *around* third-party tools (e.g. `bin/secrets sync --provider fly` shells out to `fly secrets set`). When the wrapper misbehaves, file a ticket — even if the root cause is in `fly` itself, the wrapper is ours and we can either work around it or document the constraint clearly.

## Rule 2 in practice — the smoke-test matrix

Before opening a PR that touches CLI code, run *every* subcommand of the modified CLI(s) live. Even ones that don't appear directly affected by your change. Shared utilities, argparse parents, config loaders, and output formatters routinely break adjacent subcommands.

The PR description includes a matrix:

```markdown
## Smoke-test matrix

✅ bin/logs errors --since 6h
✅ bin/logs slow --since 1h
✅ bin/logs tail --limit 50
✅ bin/logs path /api/v1/foo --since 1h
✅ bin/logs request <known-id>
✅ bin/logs inngest some-fn-id --since 7d
✅ bin/logs query "level == 'error'" --since 1h
✅ bin/logs apl "['fly-logs'] | take 5"
✅ bin/logs count "status >= 500" --since 1d
✅ bin/logs endpoints --since 6h
✅ bin/logs fields
✅ bin/logs summary --since 1h
⏸️ bin/logs health  # blocked on rotation of AXIOM_API_TOKEN — PROJ-NNNN
```

⏸️ means "couldn't test because of a blocker, filed PROJ-NNNN to unblock." If the untested subcommand is unrelated to the change, ship the PR; if it's the hot path, hold the PR until unblocked.

### Why no CLI tests in CI

Mocked CLI tests verify your code's internal behaviour but not its integration with the real backend — which is where CLIs actually fail. The parser-drift incident is the canonical example: comprehensive mocked tests passed for months while the real command silently returned empty results.

Use unit tests for **regression detection** (when you fix a bug, add a test that fails on the buggy code path), not for primary verification. Primary verification is the smoke-test matrix.

## Rule 3 in practice — maximalism + documentation

A "thin" wrapper exposes only the immediate use case. A "maximalist" wrapper exposes every reasonably useful capability of the underlying API.

**Thin** (don't do this):
```bash
bin/posthog query "SELECT count() FROM events"  # only HogQL exposed
```

**Maximalist** (do this):
```bash
bin/posthog events --since 1h            # event-type breakdown
bin/posthog event opportunities_viewed   # one event's recent rows
bin/posthog recordings --since 1h        # session replay metadata
bin/posthog recording <session-id>       # one recording's metadata
bin/posthog llm --since 7d               # $ai_generation cost/tokens
bin/posthog config                       # project settings
bin/posthog hogql "SELECT ..."           # raw HogQL
bin/posthog health                       # token + project ping
bin/posthog help                         # extended help
```

The thin version forces the agent to drop down to raw `curl` for anything beyond the one supported case. The maximalist version means the next agent never has to learn the API again.

### Output formats

Three modes, no exceptions:

| Mode | When |
|---|---|
| `pretty` | TTY default — aligned tables, human-readable, optional ANSI colour |
| `jsonl` | piped default — one JSON object per line, no surrounding array |
| `json`, `csv`, `raw` | explicit `--format` override |

Detect TTY with `sys.stdout.isatty()` and switch automatically; let users override with `--format`. Respect `NO_COLOR` env var and a `--no-color` flag.

### Exit codes

| Code | Meaning | Example |
|---|---|---|
| `0` | success | query returned rows; or returned zero rows because the dataset is genuinely empty |
| `1` | expected error | missing API token, bad APL syntax, 404 response, invalid `--since` value |
| `2` | unexpected drift | response shape changed, missing expected field, type mismatch — **treat as an incident** |
| `3` | network / API error | 5xx response, timeout, DNS failure, JSON decode failure |

Exit `2` is the load-bearing one. It's the difference between "the world is fine, results are empty" and "the world changed under us, results were silently dropped." Validate response shapes before parsing; emit `2` with a structured error naming the failed expectation.

### Documentation is part of the deliverable

The same PR that ships a new subcommand must include:

1. Inline `--help` (top-level + per-subcommand) with at least one example per subcommand.
2. `docs/operations/<cli>-cli-reference.md` (use [`cli-reference-template.md`](cli-reference-template.md)).
3. A row in CLAUDE.md § Skills & CLI Reference table.
4. A `reference_<cli>.md` entry in agent memory if the CLI has agent-relevant gotchas.

If documentation lands in a follow-up PR, it never lands. Bundle it.

## Anti-patterns

These map to the four CLI anti-patterns in `CORE.md`:

- **Smoke-test gap** — Don't ship a CLI PR without smoke-testing every command of the modified CLI. Live local runs only; document the matrix.
- **CLI tests in GHA** — Don't add CLI tests to CI. Local live tests are the source of truth. CI tests of CLIs tend to mock the world and pass while the real command is broken.
- **Thin wrappers** — Don't ship CLIs without inline help, a `docs/operations/<cli>-cli-reference.md`, and a row in CLAUDE.md. All in the same PR.
- **Silent CLI errors** — Don't silently retry or ignore CLI errors. Classify every error: agent's fault → memory file; CLI's fault → Urgent ticket + DX-channel post.

## See also

- [`agent_instructions/CLI.md`](../../agent_instructions/CLI.md) — the doctrine itself, agent-loaded
- [`recipes/cli/cli-reference-template.md`](cli-reference-template.md) — Markdown template for new CLI ref docs
- [`bin/ci-local`](../../bin/ci-local) — runs all locally-runnable CI checks in one command
