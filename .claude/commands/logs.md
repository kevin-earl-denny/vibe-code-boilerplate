---
description: Query Axiom application logs to investigate production issues
---

# /logs - Query Axiom Application Logs

Investigate application logs from your backend. Logs are shipped to Axiom (dataset configurable via `AXIOM_DATASET`) with structured JSON fields (`request_id`, `method`, `path`, `status`, `duration_ms`, `level`, etc.).

> **First time on this project?** Read [`docs/operations/logs-cli-reference.md`](../../docs/operations/logs-cli-reference.md) for the full CLI reference, then come back here for the investigation playbook. If `bin/logs health` fails, check [`recipes/observability/axiom.md`](../../recipes/observability/axiom.md) — it covers Axiom setup end-to-end.

## Setup

The CLI reads three env vars from `.env.local`:

- `AXIOM_API_TOKEN` — Personal Token with read access to the dataset
- `AXIOM_ORG_ID` — Your Axiom organisation ID
- `AXIOM_DATASET` — Defaults to `app-logs`

Run `bin/logs health` to verify the token works and the dataset is reachable.

## Investigation playbook

If your project has [`docs/operations/app-routes-and-jobs.md`](../../docs/operations/app-routes-and-jobs.md), read that first to map the user's description to the correct API endpoints or job IDs. Without that file, the playbook still works — you'll just spend more time guessing the right path prefix.

### Step 1: Pick a preset

There's almost always a subcommand that does what you need. Reach for it before writing a free-form query.

| Symptom user reports | Subcommand |
|---|---|
| Page broken / 5xx | `bin/logs query "status >= 500 and path startswith '/api/X'" --since 6h` |
| Page slow | `bin/logs slow --since 1h --threshold 2000` |
| Specific request id (Sentry, frontend trace) | `bin/logs request <id>` |
| All traffic to a route | `bin/logs path /api/X --since 1h` |
| Background job failed | `bin/logs inngest <function-id> --since 3d` |
| "Did anything run last night?" | `bin/logs inngest <function-id> --since 24h` |
| What's broken right now? | `bin/logs summary --since 1h` |
| Latency budget overview | `bin/logs endpoints --since 6h` |
| Quick "is the backend even up?" | `bin/logs health` |

### Step 2: Narrow with `query` if needed

```bash
# Free-form where-clause (interpolated into | where ...)
bin/logs query "level == 'error' and path startswith '/api/users'" --since 6h

# Full APL when you need joins, summaries, or extends
bin/logs apl "['app-logs'] | where status >= 500 | sort by _time desc | take 20"

# When quoting gets ugly (single + double quotes), use stdin
cat <<'APL' | bin/logs apl - --since 24h
['app-logs']
| where path contains '/api/'
| summarize p95=percentile(duration_ms,95) by bin(_time, 1h), path
| sort by _time desc
APL
```

Replace `app-logs` with your configured `AXIOM_DATASET`.

### Step 3: Reformat for the audience

- Sharing in a ticket / Slack? `--format csv --fields _time,path,status,duration_ms,request_id > out.csv`
- Piping to `jq`? Default is jsonl when piped — no flag needed.
- Need the full API response (e.g., to debug the parser)? `--format raw`.

### Step 4: Interpret

- Group errors by endpoint or function
- Note error frequency and timing patterns
- Check if errors correlate with recent deployments
- For OOM issues, check memory-related logs and consider reducing batch sizes

## Common scenarios

### "The /users page is broken"
```bash
bin/logs query "path startswith '/api/users/' and status >= 400" --since 6h
```

### "API requests are slow"
```bash
bin/logs slow --threshold 1000 --since 1h
bin/logs endpoints --since 6h | sort by p95 desc
```

### "Did the nightly job run?"
```bash
bin/logs inngest <your-job-id> --since 48h
```

### "Trace this Sentry request"
```bash
bin/logs request <request-id-from-Sentry>
```

### "An Inngest function failed but I don't see the alert"
```bash
bin/logs apl "['app-logs'] | where event == 'inngest/function.failed' | sort by _time desc | take 50"
```

## Things that bite

- **Default `--since` is `1h`.** Cron jobs run daily-to-weekly — bump to `--since 7d` or `--since 14d` for ingest activity.
- **`message` is not a field — it's `msg`.** APL throws `invalid field: "message"` if you write the wrong one.
- **Most `logger_name` values may be `null`** if your structlog flattening filter doesn't apply to stdlib loggers (Inngest, raw `logging.info`). Fall back to: `bin/logs apl "['app-logs'] | where msg contains 'pattern'"`.
- **Inngest health-check requests can look pathologically slow** (10+ minutes p95) because Inngest blocks the HTTP request until the step completes. Filter them out: `path != '/api/inngest'`.
- **Exit code 2 = parser drift.** The CLI loudly fails when Axiom's response shape changes. Treat as an incident, not a flake; check `tables[0]` keys via `--format raw`.

## When `bin/logs` isn't enough

The CLI is a thin wrapper over Axiom's APL endpoint. For ad-hoc exploration with a real query builder, jump to the Axiom UI: [app.axiom.co](https://app.axiom.co). Saved queries and dashboards live there.

## Reference

- Full CLI reference: [`docs/operations/logs-cli-reference.md`](../../docs/operations/logs-cli-reference.md)
- Backend setup: [`recipes/observability/axiom.md`](../../recipes/observability/axiom.md)
- Routes & job IDs: `docs/operations/app-routes-and-jobs.md` (if your project maintains one)

$ARGUMENTS
