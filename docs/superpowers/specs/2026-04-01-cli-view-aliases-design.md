# CLI View Aliases for Linear Board Views

**Issue:** #278
**Date:** 2026-04-01
**Approach:** Option C — Sync from Linear API

## Summary

Add `--view` and `--unblocked` flags to `bin/ticket list` that fetch named Linear custom views via GraphQL and use their saved filters. Linear-only.

## Architecture

### New CLI surface

```bash
bin/ticket list --view "Active"                # Use Linear custom view filter
bin/ticket list --view "Backlog" --unblocked   # Combine with unblocked post-filter
bin/ticket views                               # List available custom views
```

### `--view NAME` flag

1. Query `customViews` from Linear API (cached 30 min)
2. Find view by name (case-insensitive match)
3. Extract `filterData` JSON — same shape as `IssueFilter`, pass directly to `issues()` query
4. Merge with team filter (always scope to configured team)
5. Explicit CLI filters (`--status`, `--label`, etc.) merge into/override the view filter

Error handling:
- View not found: error listing available view names
- Ambiguous match: error asking user to be specific

### `--unblocked` flag

Client-side post-filter that removes tickets with blocking dependencies:

1. Add `inverseRelations { nodes { type } }` to the list issues query
2. After fetching, exclude tickets where any inverse relation has `type == "blocks"`
3. Works standalone or combined with `--view`

### New methods on `LinearTracker`

- `list_views() -> list[dict]` — fetch all custom views, cached 30 min
- `_get_view_filter(view_name: str) -> dict` — get filterData for named view

### `bin/ticket views` subcommand

Lists available Linear custom views with name and owner.

## Files to modify

| File | Change |
|------|--------|
| `lib/vibe/trackers/linear.py` | `list_views()`, `_get_view_filter()`, `view`/`unblocked` params on `list_tickets()`, `inverseRelations` in query |
| `lib/vibe/cli/ticket.py` | `--view`, `--unblocked` options on `list`, new `views` subcommand |
| `lib/vibe/trackers/base.py` | Add `view`/`unblocked` to base `list_tickets()` signature |
| `lib/vibe/config_schema.py` | Add `"views"` to `KNOWN_KEYS` |
| `tests/test_views.py` | Tests for view fetching, filter merging, unblocked filtering |

## Out of scope

- Config-driven view overrides
- Shortcut/GitHub tracker support
- View creation/editing via CLI
