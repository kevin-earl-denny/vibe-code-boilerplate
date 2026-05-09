# Core Agent Instructions

This is the single source of truth for AI agent instructions. Edit this file to change behavior across all assistants.

## Project Overview

Fill these in for your project:

- **Name**: (your project name)
- **Description**: (what this project does)

## Tech Stack

- Backend: (e.g., FastAPI, Django, Express)
- Frontend: (e.g., React, Next.js, Vue)
- Database: (e.g., PostgreSQL, Supabase, Neon)
- Deployment: (e.g., Vercel, Fly.io, AWS)

## Core Rules

These rules MUST be followed by all AI assistants:

- Read files before modifying them - understand existing code before making changes
- Use existing patterns - match the codebase's style, naming conventions, and architecture
- Prefer editing over creating - modify existing files rather than creating new ones
- Keep changes minimal - only change what's necessary to complete the task
- No security vulnerabilities - avoid XSS, SQL injection, command injection, etc.
- Handle errors gracefully - don't leave code in broken states
- Test your changes - verify code works before marking task complete
- Document non-obvious code - add comments only where the logic isn't self-evident
- Every PR must reference a ticket - PR titles must include the ticket ID (e.g. "PROJ-123: Add feature")
- Every ticket must have labels - at minimum one type label (Bug/Feature/Chore/Refactor), one risk label (Low Risk/Medium Risk/High Risk), and one area label (Frontend/Backend/Infra/Docs)
- Set parent/child relationships for related tickets - use --parent when creating sub-tasks
- Use blocking links for dependencies - the prerequisite ticket blocks the dependent ticket

## Anti-Patterns

Avoid these common mistakes:

- Guessing file contents without reading them first
- Creating new abstractions for one-time operations
- Adding features, refactoring, or "improvements" beyond what was asked
- Over-engineering with unnecessary complexity
- Leaving console.log or debug statements in production code
- Ignoring existing error handling patterns
- Making assumptions about requirements without asking
- Committing secrets, API keys, or credentials
- Creating tickets without labels - every ticket needs type, risk, and area labels
- Opening PRs without a ticket reference in the title
- Creating related tickets without parent/child or blocking relationships
- **Shipping a CLI PR without smoke-testing every command of the modified CLI** — see `CLI.md`. Live local runs only; document the test matrix (✅/❌/⏸️) in the PR description. ⏸️ requires a `<CLI>: test + fix <command>` follow-up ticket.
- **Adding CLI tests to GitHub Actions** — local live tests are the source of truth. CI tests of CLIs tend to mock the world and pass while the real command is broken. Test files are for regression detection, not primary verification.
- **Shipping thin CLI wrappers** — see `CLI.md`. Default to maximalist surface area + thorough docs. Inline `--help` + `docs/operations/<cli>-cli-reference.md` + a row in CLAUDE.md Skills/CLI table all land in the same PR as the new subcommand.
- **Silently retrying or ignoring CLI errors** — classify every error: agent's fault → write a feedback memory file (`feedback_cli_<cli>_<topic>.md`); CLI's fault → file an Urgent Linear ticket and post to your CLI/agent-DX discussion channel. Any DX papercut qualifies — the bar is intentionally low.

## CLI Conventions

The full doctrine for `bin/*` wrappers lives in [`CLI.md`](CLI.md). Three rules in summary:

1. **Reliability — capture or file.** Every CLI error gets either a memory entry (agent's fault) or an Urgent ticket + DX-channel post (CLI's fault).
2. **Pre-PR testing — smoke-test every subcommand.** Live local runs only. Document the matrix (✅/❌/⏸️) in the PR description.
3. **Maximalist + documented.** Ship every useful subcommand at once; same-PR docs (inline `--help` + `docs/operations/<cli>-cli-reference.md` + CLAUDE.md row). Output formats: pretty / jsonl / `--format`. Exit codes: `0`/`1`/`2`/`3` per the standard scheme — `2` is **parser drift** and should be treated as an incident, not a flake.

`bin/ci-local` runs all locally-runnable CI checks in one command — run it before pushing.

## Important Files

Key files to be aware of:

- `CLAUDE.md` - AI agent instructions (this generated file)
- `.vibe/config.json` - Project configuration
- `README.md` - Project documentation
- `.env.example` - Environment variable template

## Linear Projects

Fill this in when Linear Projects are set up for your project (see `recipes/tickets/linear-projects.md`):

| Project | State | Description |
|---------|-------|-------------|
| *(add projects here)* | | |

When creating tickets, assign to the appropriate project with `--project "Name"`.
