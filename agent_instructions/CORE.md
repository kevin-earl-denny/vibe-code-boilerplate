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
