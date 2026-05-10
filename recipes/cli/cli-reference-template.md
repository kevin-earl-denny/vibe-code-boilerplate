# `<cli-name>` CLI Reference Template

Copy this file to `docs/operations/<cli-name>-cli-reference.md` when adding a new `bin/<cli-name>` CLI. Fill in every section. The structure is mandatory; the content is yours.

This template was modelled on the per-subcommand structure that proved most useful for agent-driven debugging — quick-reference at top, subcommand catalogue table, per-subcommand detail, common patterns, exit codes, and token rotation.

---

```markdown
---
title: bin/<cli-name> — CLI reference
date: <YYYY-MM-DD>
author: <author>
status: active
related_tickets: [PROJ-NNNN]
---

# bin/<cli-name> — CLI reference

<One-paragraph description: what backend does this CLI talk to, what does it
let you do, what is the relationship to other CLIs in this project. Link to
the architecture doc if there is one (e.g. observability.md for bin/logs).>

The CLI is a thin wrapper over <backend>'s <API endpoint(s)>. Every subcommand
ultimately <how the request is constructed>, parses the <response shape>, and
prints rows.

> **Why this CLI exists in this shape:** <one paragraph of design history.
> What problem motivated this CLI? What earlier version existed and why was
> it replaced? What incidents shaped the current design? — at minimum, mention
> the exit-code-2-on-drift behaviour if applicable.>

---

## Quick reference

\```bash
bin/<cli> help                           # Print extended help
bin/<cli> health                         # Token / connectivity check

# Common presets
bin/<cli> errors --since 6h
bin/<cli> tail --limit 50

# Aggregations / queries
bin/<cli> query "<filter>" --since 1h
bin/<cli> apl "<full query>"
echo "<query>" | bin/<cli> apl -          # query via stdin

# Free-form
bin/<cli> raw "<...>"
\```

---

## Subcommand catalogue

| Subcommand | Purpose | Required arg |
|---|---|---|
| `errors` | <one-line> | – |
| `tail` | <one-line> | – |
| `query WHERE` | <one-line> | filter clause |
| `health` | <one-line> | – |
| `help` | Print extended help | – |

---

## Subcommand reference

### `errors`

<Full description: when do you reach for this subcommand, what does it filter
on, what's the default time window.>

\```bash
bin/<cli> errors --since 6h
bin/<cli> errors --since 24h --limit 100
\```

| Flag | Description | Default |
|---|---|---|
| `--since` | Lookback window (`30s`, `5m`, `2h`, `7d`, ISO-8601) | `1h` |
| `--until` | End of window | `now` |
| `--limit` | Max rows | `30` |
| `--format` | `pretty\|json\|jsonl\|raw\|csv\|auto` | `auto` |
| `--fields` | Comma-separated field list to display | (default set) |
| `-v / --verbose` | Show full row data, not just default fields | off |
| `--no-color` | Disable ANSI colour | off |

<Repeat for every subcommand.>

---

## Common patterns

### Pipe to jq

\```bash
bin/<cli> query "<filter>" --since 1h | jq '.[] | {field1, field2}'
\```

When stdout is piped, the default format is `jsonl` — no flag needed.

### Save to CSV for sharing

\```bash
bin/<cli> query "<filter>" --since 1d --format csv \\
  --fields _time,field1,field2 > out.csv
\```

### Investigation playbook

<Either inline a quick playbook here, or point to .claude/commands/<cli>.md.>

---

## Output formats

The CLI auto-detects context:
- **TTY (default)** → `pretty` — aligned tables with optional colour
- **piped (default)** → `jsonl` — one JSON object per line
- **explicit override** → `--format pretty|json|jsonl|raw|csv`

`raw` returns the full backend response (useful for debugging the parser itself).

---

## Exit codes

| Code | Meaning | When you'll see it |
|---|---|---|
| `0` | success | query returned rows; or genuinely-empty result |
| `1` | expected error | bad args, missing token, 4xx response, validation failure |
| `2` | parser drift | response shape changed; **treat as an incident, not a flake** |
| `3` | network / API error | timeout, DNS, 5xx, JSON decode failure |

**Exit code 2 is load-bearing.** When you see it, treat it as an incident: the
backend changed its response shape and the CLI refused to silently return empty
results. Inspect `tables[0]` keys via `--format raw` and update the parser.

---

## Configuration

| Variable | Where | Value |
|---|---|---|
| `<TOKEN_VAR>` | `.env.local` + production secrets | API token (scoped to <minimum permissions>) |
| `<HOST_VAR>` | `.env.local` | <default> |
| `<DATASET_VAR>` | `.env.local` | <default> |

`bin/<cli>` reads the token from `.env.local` automatically. In production,
fetch from your secrets store (e.g. `fly secrets list`).

### Token rotation

\```bash
# 1. Create new token in <provider> console (scoped: <permissions>)
# 2. Update production secrets
<provider> secrets set <TOKEN_VAR>=<value>

# 3. Update .env.local for local CLI usage
# 4. Revoke the old token
\```

---

## Things that have bitten us

<List 3-7 gotchas the agent should know about. Be specific. Examples:>

- **Default `--since` is `1h`.** ETL/cron jobs run daily-to-weekly — bump to `--since 7d` when looking for cron activity.
- **`<field-x>` is mostly null** because <reason>. When that field returns nothing, fall back to `<alternative>`.
- **`<field-y>` is named `<actual-name>`, not `<intuitive-name>`.** APL throws if you write the wrong one.
- **Exit code 2 = parser drift.** The CLI loudly fails when <backend>'s response shape changes. Treat as an incident.

---

## When `bin/<cli>` isn't enough

The CLI is a thin wrapper over <backend>'s API. For ad-hoc exploration with a
real query builder, jump to <backend>'s UI: <link>. Saved queries and dashboards
live there.

---

## Reference

- Investigation playbook: `.claude/commands/<cli>.md`
- Architecture: `docs/operations/<related-architecture-doc>.md`
- Source: `bin/<cli>` (and `lib/vibe/cli/<cli>.py` if implementation is split)
```
