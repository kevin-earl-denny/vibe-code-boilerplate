---
title: bin/logs — CLI reference
status: active
---

# bin/logs — CLI reference

Self-contained Python CLI for querying an Axiom log dataset. This doc is the single source of truth for **how** to use the CLI; for **why** logs end up in Axiom and how the pipeline is built, see [`recipes/observability/axiom.md`](../../recipes/observability/axiom.md). For the `/logs` skill investigation playbook, see [`.claude/commands/logs.md`](../../.claude/commands/logs.md).

The CLI is a thin wrapper over Axiom's APL endpoint. Every subcommand ultimately POSTs to `https://api.axiom.co/v1/datasets/_apl?format=tabular`, parses the column-major response, and prints rows.

> **Why exit code 2 matters.** A previous bash incarnation of this CLI parsed `tables[0].rows`, but Axiom's tabular format is column-major (`tables[0].columns`). Every query silently returned `"No results."` for weeks. The Python rewrite added drift detection — if Axiom's response shape ever changes again, the CLI fails loudly with exit code `2` instead of pretending the dataset is empty. This pattern is codified in [`agent_instructions/CLI.md`](../../agent_instructions/CLI.md) Rule 3.

---

## Quick reference

```bash
bin/logs                                  # Print extended help
bin/logs help                             # Same
bin/logs examples                         # Print common APL recipes
bin/logs health                           # Token / dataset connectivity check

# Investigation presets
bin/logs errors --since 6h                # Recent error / critical
bin/logs slow --since 1h --threshold 2000 # Slow HTTP requests
bin/logs tail --limit 50                  # Latest events across all sources
bin/logs path /api/users/                 # Logs for an HTTP path prefix
bin/logs request <request-id>             # All logs for one request
bin/logs inngest <function-id> --since 7d # Background job logs

# Aggregations
bin/logs summary --since 1h               # Birds-eye dashboard
bin/logs endpoints --since 6h             # Per-path p50/p95/p99
bin/logs count "status >= 500" --since 1d # Just print rowsMatched
bin/logs fields                           # List dataset field names + types

# Free-form
bin/logs query "level == 'error' and path startswith '/api/'"
bin/logs apl "['app-logs'] | take 5"
echo "['app-logs'] | take 5" | bin/logs apl -    # APL via stdin
```

Replace `app-logs` with your configured `AXIOM_DATASET`.

---

## Subcommand catalogue

| Subcommand | Purpose | Required arg |
|---|---|---|
| `errors` | Most recent `error` / `critical` rows | – |
| `slow` | HTTP requests with `duration_ms > --threshold` (default 2000) | – |
| `tail` | Most recent rows across the dataset | – |
| `path PREFIX` | Rows whose `path` starts with `PREFIX` | path prefix |
| `request RID` | All rows for one `request_id`, sorted oldest-first | request UUID |
| `inngest FN_ID` | Inngest function logs (case-insensitive across logger / msg / event) | function id |
| `query WHERE` | Free-form `\| where WHERE` filter | APL where-clause |
| `apl APL_QUERY` | Raw APL. Pass `-` to read from stdin | APL or `-` |
| `count [WHERE]` | Print just the matched-row count (uses `summarize n=count()`) | optional where |
| `endpoints` | Per-path latency table (n, p50, p95, p99, max) | – |
| `fields` | List dataset fields with types | – |
| `summary` | Errors + slow + top paths + top error sources, in one shot | – |
| `health` | Token loaded? API reachable? Recent data? Response-shape sanity? | – |
| `examples` | Print common APL recipes | – |
| `help` | Print extended help | – |

---

## Flags (common across subcommands)

| Flag | Description | Default |
|---|---|---|
| `--since` | Lookback window (`30s`, `5m`, `2h`, `7d`, ISO-8601, `today`, `yesterday`) | `1h` |
| `--until` | End of window (same formats as `--since`) | `now` |
| `--limit` | Max rows | `50` (max ~1000) |
| `--threshold` | For `slow` and `summary` (ms) | `2000` |
| `--format` | `pretty\|json\|jsonl\|raw\|csv\|auto` | `auto` |
| `--fields` | Comma-separated field list to display | (default set) |
| `--all-fields` | Show every field returned (verbose pretty) | off |
| `-v / --verbose` | Print rowsMatched / elapsedTime to stderr | off |
| `--dry-run` | Print the APL + time range without executing | off |
| `--no-color` | Disable ANSI colours (also: `NO_COLOR` env var) | off |

---

## Output formats

The CLI auto-detects context:
- **TTY (default)** → `pretty` — aligned tables with optional ANSI colour
- **piped (default)** → `jsonl` — one JSON object per line (`bin/logs ... | jq` works without flags)
- **explicit override** → `--format pretty|json|jsonl|raw|csv`

`raw` returns the full Axiom API response — useful when debugging the parser itself or chasing exit code 2 incidents.

The default field set for `pretty` and `csv`:

```
_time, level, logger_name, method, path, status, duration_ms, event, request_id
```

Override with `--fields a,b,c`. Add `--all-fields` to dump everything Axiom returns for each row.

---

## Exit codes

| Code | Meaning | When you'll see it |
|---|---|---|
| `0` | success | query returned rows; or genuinely-empty result |
| `1` | expected error | bad args, missing token, 4xx response, validation failure |
| `2` | parser drift | response shape changed; **treat as an incident, not a flake** |
| `3` | network / API error | timeout, DNS, 5xx, JSON decode failure |

**Exit code 2 is load-bearing.** When you see it, treat it as an incident: Axiom changed its response shape and the CLI refused to silently return empty results. Inspect `tables[0]` keys via `--format raw` and update the parser. (See the parser-drift incident in [`agent_instructions/CLI.md`](../../agent_instructions/CLI.md) for the canonical example.)

---

## Configuration

| Variable | Where | Value |
|---|---|---|
| `AXIOM_API_TOKEN` | `.env.local` + production secrets | Personal Token (Ingest + Query scope) |
| `AXIOM_ORG_ID` | `.env.local` + production secrets | Your Axiom organisation ID |
| `AXIOM_DATASET` | `.env.local` + production secrets | Dataset name (default: `app-logs`) |

`bin/logs` reads from `.env.local` automatically. In production, fetch via your secrets store (`fly secrets list`, `vercel env pull`, etc.).

### Token rotation

```bash
# 1. Create a new token in Axiom (Settings → API Tokens, "Ingest + Query" scope)
# 2. Update production secrets — choose your platform
fly secrets set AXIOM_API_TOKEN=xapt-... --app <your-app>
vercel env add AXIOM_API_TOKEN production
gh secret set AXIOM_API_TOKEN --app actions

# 3. Update .env.local for local bin/logs usage
# 4. Verify
bin/logs health

# 5. Revoke the old token in Axiom
```

The non-blocking handler design means the brief window where both tokens work is fine — old token starts failing silently (logs go to console only) until the next deploy picks up the new value.

---

## Common patterns

### Pipe to jq

```bash
bin/logs query "level == 'error'" --since 1h | jq '.[] | {request_id, path, status}'
```

When stdout is piped, the default format is `jsonl` — no flag needed.

### Save to CSV for sharing

```bash
bin/logs query "status >= 500" --since 1d --format csv \
  --fields _time,path,status,duration_ms,request_id > slow-errors.csv
```

### Investigate a single user complaint

```bash
# Get the request_id from a Sentry issue or frontend trace
bin/logs request abc-123-def
```

### Latency budget per route

```bash
bin/logs endpoints --since 6h | sort by p95 desc | head -20
```

### Hourly rollup of errors

```bash
cat <<'APL' | bin/logs apl - --since 24h
['app-logs']
| where level in ('error', 'critical')
| summarize n=count() by bin(_time, 1h), logger_name
| sort by _time asc
APL
```

---

## Things that bite

- **Default `--since` is `1h`.** Cron jobs run daily-to-weekly — bump to `--since 7d` or `--since 14d` when looking for ingest activity.
- **`message` is not a field — it's `msg`.** APL throws `invalid field: "message"` if you write the wrong one. The CLI uses `msg` everywhere.
- **`logger_name` may be null** for stdlib loggers (Inngest, `logging.info`) when the structlog flattening filter doesn't apply. Fall back to `where msg contains '<pattern>'` if `inngest <fn-id>` returns nothing useful.
- **`/api/inngest` requests look pathologically slow** (10+ minutes p95). That's expected — Inngest blocks the HTTP request until the step completes. Filter with `path != '/api/inngest'` for user-facing latency.
- **Exit code 2 = parser drift.** Treat as an incident, not a flake. Check `tables[0]` keys via `--format raw`.

---

## When `bin/logs` isn't enough

The CLI is a thin wrapper over Axiom's APL endpoint. For ad-hoc exploration with a real query builder, jump to the Axiom UI at [app.axiom.co](https://app.axiom.co). Saved queries, dashboards, and alerts live there.

---

## See also

- [`recipes/observability/axiom.md`](../../recipes/observability/axiom.md) — backend setup recipe (provisioning, log shipping, flattening filter)
- [`.claude/commands/logs.md`](../../.claude/commands/logs.md) — `/logs` skill investigation playbook
- [`agent_instructions/CLI.md`](../../agent_instructions/CLI.md) — CLI conventions doctrine (this CLI follows it)
- [`recipes/cli/cli-reference-template.md`](../../recipes/cli/cli-reference-template.md) — template for new `<cli>-cli-reference.md` files (this doc was modelled on it)
- Axiom docs: [APL reference](https://axiom.co/docs/apl/introduction)
