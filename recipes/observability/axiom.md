# Recipe: Axiom for Application Logs

[Axiom](https://axiom.co) is a hosted log + analytics backend with a generous free tier (~500 GB/month) and a clean APL query language. This recipe covers the full pipeline:

1. Provisioning a free Axiom account + dataset
2. Configuring the env vars in `.env.local`
3. Shipping structured logs from your backend
4. Querying via the `bin/logs` CLI (15 subcommands; see [`docs/operations/logs-cli-reference.md`](../../docs/operations/logs-cli-reference.md))
5. Wiring the `/logs` Claude Code skill to your project's routes/jobs
6. Token rotation procedure

If you only care about the CLI: configure the three env vars, run `bin/logs health`, and you're done. The backend log-shipping setup is what makes the CLI useful — without it you have an empty dataset.

## Why Axiom (vs alternatives)

The boilerplate is opinionated about Axiom because:

| Concern | Axiom | Self-hosted Loki | OTel + Grafana Cloud |
|---|---|---|---|
| Setup friction | ~5 min: token + handler | Hours: docker, ingester, query frontend | Hours: collector, exporters, dashboards |
| Free tier | ~500 GB/month | Self-hosted only | 50 GB/month |
| Query language | APL (clean, KQL-like) | LogQL | LogQL/PromQL |
| Native structured-JSON | Yes | Yes | Yes |
| Retention | ~14 days on free tier | Configurable | 30 days |
| Cost predictability | Per-GB ingest | Free if you self-host | Per-GB ingest |

For most projects, "I want logs to be queryable from a CLI without spending an afternoon" is the dominant constraint. Axiom is hard to beat there. If your project has compliance constraints requiring self-hosted, Loki is the alternative — but expect a meaningful infrastructure investment.

## 1. Provision an Axiom account + dataset

1. Sign up at [app.axiom.co](https://app.axiom.co) (free tier).
2. Create a new dataset. Naming convention recommendation: `<project>-logs` (e.g. `myapp-logs`).
3. Settings → API Tokens → Create Token. Scope: "Ingest + Query". Save the token; you can't see it again.
4. Note your Org ID (Settings → General → top of page).

## 2. Configure env vars

Add to `.env.local` (and to your production secrets store):

```bash
AXIOM_API_TOKEN=xapt-<your-token>
AXIOM_ORG_ID=<your-org-id>
AXIOM_DATASET=<your-project>-logs   # default: "app-logs" if unset
```

If you use [Vercel](../deployment/vercel.md) or [Fly.io](../deployment/fly-io.md), sync these to production via `bin/secrets sync`.

Verify locally:

```bash
bin/logs health
```

You should see `Token: OK`, `API: OK`, `Recent data: …` (or "no rows yet" if no logs have shipped).

## 3. Ship structured logs from your backend

The CLI is only useful if your backend ships structured logs to the dataset. The shape is up to you, but the recommended fields (the CLI's defaults assume them):

| Field | Purpose |
|---|---|
| `_time` | Axiom timestamp (set automatically) |
| `level` | `debug` / `info` / `warning` / `error` / `critical` |
| `event` | Short event name (e.g. `request`, `step_complete`, `request_error`) |
| `logger_name` | Module path (e.g. `api.routes.users`) |
| `request_id` | Per-request correlation UUID |
| `path` | HTTP request path (for HTTP middleware logs) |
| `method` | HTTP method |
| `status` | HTTP status code |
| `duration_ms` | Request duration in ms |
| `msg` | Human-readable message |

These match what the `bin/logs` CLI's `slow`, `path`, `request`, `endpoints`, and `summary` subcommands expect. You can use any other field schema — the CLI still works, but you'll lean more on `bin/logs apl "<query>"` raw queries.

### FastAPI / Python — `axiom-py` SDK

Install:

```bash
uv add axiom-py structlog
# or: pip install axiom-py structlog
```

Add a logging-handler integration. The critical detail is **flattening** — see [Field Flattening Gotcha](#field-flattening-gotcha) below.

```python
# api/logging.py
import logging
import os
import sys
import structlog


def setup_logging() -> None:
    """Configure structlog + stdlib logging + Axiom shipping (if configured)."""
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, level, logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    is_production = os.environ.get("APP_ENV") == "production"
    renderer = (
        structlog.processors.JSONRenderer()
        if is_production
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(log_level)

    # Ship to Axiom in production when configured. Failure here is non-fatal.
    if is_production and os.environ.get("AXIOM_API_TOKEN"):
        _attach_axiom_handler(root, log_level)


def _attach_axiom_handler(root_logger: logging.Logger, level: int) -> None:
    try:
        import axiom_py
        from axiom_py.logging import AxiomHandler
    except ImportError:
        root_logger.warning("axiom-py not installed — skipping Axiom shipping")
        return

    try:
        client = axiom_py.Client(
            token=os.environ["AXIOM_API_TOKEN"],
            org_id=os.environ["AXIOM_ORG_ID"],
        )
        handler = AxiomHandler(
            client,
            os.environ.get("AXIOM_DATASET", "app-logs"),
            level=level,
        )
        handler.addFilter(_StructlogFlatteningFilter())
        root_logger.addHandler(handler)
        root_logger.info("Axiom shipping enabled")
    except Exception as exc:  # noqa: BLE001
        root_logger.warning("Axiom shipping failed to start: %s", exc)


class _StructlogFlatteningFilter(logging.Filter):
    """Promote structlog event-dict keys to top-level LogRecord attrs.

    Without this, every structured field ends up nested under `msg` and is
    invisible to top-level APL queries like `where path startswith '/api/'`.
    """

    _RESERVED = frozenset({
        "args", "created", "exc_info", "exc_text", "filename", "funcName",
        "levelname", "levelno", "lineno", "message", "module", "msecs", "msg",
        "name", "pathname", "process", "processName", "relativeCreated",
        "stack_info", "thread", "threadName",
    })

    def filter(self, record: logging.LogRecord) -> bool:
        if not isinstance(record.msg, dict):
            return True
        event_dict = record.msg
        for key, value in event_dict.items():
            target = f"ctx_{key}" if key in self._RESERVED else key
            setattr(record, target, value)
        if "logger" in event_dict and not hasattr(record, "logger_name"):
            record.logger_name = event_dict["logger"]  # type: ignore[attr-defined]
        record.msg = event_dict.get("event", "")
        return True
```

Call `setup_logging()` once at app startup. In FastAPI, do this before creating the app instance.

### Express / Hono / Node — `@axiomhq/js`

Install:

```bash
npm install @axiomhq/js pino pino-axiom
```

Use `pino` (or your preferred structured logger) with the Axiom transport:

```ts
// src/logger.ts
import pino from "pino"

const transport = pino.transport({
  target: "pino-axiom",
  options: {
    dataset: process.env.AXIOM_DATASET ?? "app-logs",
    token: process.env.AXIOM_API_TOKEN,
    orgId: process.env.AXIOM_ORG_ID,
  },
})

export const logger = pino({ level: process.env.LOG_LEVEL ?? "info" }, transport)
```

In each request handler:

```ts
logger.info({
  event: "request",
  request_id: crypto.randomUUID(),
  method: req.method,
  path: req.url,
  status: res.statusCode,
  duration_ms: Date.now() - start,
})
```

### Django

Use `django-axiom` (community-maintained) or implement an `AxiomHandler` similar to the Python example above. Django's logging config is in `settings.py` under `LOGGING`.

## 4. Field Flattening Gotcha

When using `structlog` with the Python `AxiomHandler`, you **must** install a flattening filter. Otherwise every structured field ends up nested under `msg` as a dict, and queries like `where path startswith '/api/'` return nothing because Axiom doesn't index nested fields.

The recipe above includes `_StructlogFlatteningFilter`. Symptoms if you skip it:

- Every Axiom row has `msg: { request_id: ..., path: ..., status: ..., }` (a dict, not a string)
- APL queries on top-level fields return zero results
- The dataset has data, but every dashboard you build is empty

If you see this pattern in your dataset, the filter isn't attached or isn't running before the handler. Check the handler setup code.

## 5. Wire the `/logs` skill

The boilerplate ships a `/logs` Claude Code skill at `.claude/commands/logs.md`. It maps user-reported symptoms to log queries — for that, it needs to know your project's API routes and background jobs.

Create `docs/operations/app-routes-and-jobs.md` (the skill reads this — see the template under [Issue #310](https://github.com/kevin-earl-denny/vibe-code-boilerplate/issues/310)). Without it, the skill is a generic CLI wrapper. With it, the skill becomes a debugging skill: "user says X is broken" → "the route map says X = `/api/v1/Y`, query that path."

## 6. Token rotation

```bash
# 1. Create a new token in Axiom (Settings → API Tokens, "Ingest + Query" scope)
# 2. Update production secrets
fly secrets set AXIOM_API_TOKEN=xapt-... --app <your-app>      # if Fly
vercel env add AXIOM_API_TOKEN production                       # if Vercel

# 3. Update .env.local for local bin/logs usage

# 4. Verify in production
bin/logs health  # against the deployed env
fly logs --app <your-app> | grep -i "axiom shipping enabled"

# 5. Revoke the old token in Axiom
```

The non-blocking handler design means a brief window where both tokens work is fine — the old token will start failing silently (logs go to console only) until the next deploy picks up the new value.

## See also

- [`docs/operations/logs-cli-reference.md`](../../docs/operations/logs-cli-reference.md) — full CLI reference
- [`.claude/commands/logs.md`](../../.claude/commands/logs.md) — `/logs` skill investigation playbook
- [`agent_instructions/CLI.md`](../../agent_instructions/CLI.md) — CLI conventions doctrine (this CLI follows it)
- [`bin/ci-local`](../../bin/ci-local) — local CI mirror; doesn't run Axiom queries but follows the same conventions
- Axiom docs: [APL reference](https://axiom.co/docs/apl/introduction)
