# AI Agent Instructions
# Format: GitHub Copilot
# Generated: 2026-04-01
# Source: agent_instructions/
#
# DO NOT EDIT DIRECTLY - regenerate with: bin/vibe generate-agent-instructions


# Copilot Instructions

## About This Project

This is **(your project name)**.
(what this project does)

## Technology Stack

- **Backend**: (e.g., FastAPI, Django, Express)
- **Frontend**: (e.g., React, Next.js, Vue)
- **Database**: (e.g., PostgreSQL, Supabase, Neon)
- **Deployment**: (e.g., Vercel, Fly.io, AWS)

## Coding Guidelines

Follow these guidelines when generating code:

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

## Available Labels

These labels are configured in `.vibe/config.json`. Apply them when creating tickets.

**Type (exactly one required):** Bug, Feature, Chore, Refactor

**Risk (exactly one required):** Low Risk, Medium Risk, High Risk

**Area (at least one required):** Frontend, Backend, Infra, Docs

**Special (as needed):** HUMAN, Milestone, Blocked

## Ticket Discipline

Follow these rules for every ticket and PR:

### Labels Are Required

Every ticket **must** have labels when created:

- **Type** (exactly one): Bug, Feature, Chore, or Refactor
- **Area** (at least one): Frontend, Backend, Infra, or Docs
- **Risk** (exactly one): Low Risk, Medium Risk, or High Risk

```bash
bin/ticket create "Fix login bug" --description "Login returns 500 on special chars." --label Bug --label Frontend --label "Low Risk"
```

### Parent/Child Relationships

When creating sub-tasks, set the parent ticket:

```bash
bin/ticket create "Add signup form" --description "React signup component." --label Feature --label Frontend --parent PROJ-100
```

### Blocking Relationships

When one ticket must be completed before another can start, link them with a blocking relationship. The prerequisite ticket blocks the dependent ticket:

```bash
bin/ticket relate PROJ-101 --blocks PROJ-102
```

### Every PR Needs a Ticket

Every pull request **must** reference a ticket. Include the ticket ID in the PR title:

```bash
bin/vibe pr --title "PROJ-123: Add user authentication"
```

## Patterns to Avoid

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

## Key Files

- ``CLAUDE.md` - AI agent instructions (this generated file)`
- ``.vibe/config.json` - Project configuration`
- ``README.md` - Project documentation`
- ``.env.example` - Environment variable template`

## CLI Commands

Use these commands for common operations:

- `bin/vibe doctor` - Check project health and configuration.
- `bin/vibe setup` - Run the setup wizard to configure your project.
- `bin/vibe do <ticket-id>` - Start working on a ticket (creates worktree and branch).
- `bin/ticket list [OPTIONS]` - List tickets from the tracker.
- `bin/ticket get <ticket-id> [OPTIONS]` - Get details for a specific ticket.
- `bin/ticket create "<title>" [OPTIONS]` - Create a new ticket. **A description is REQUIRED** — never create a ticket without one. **Labels are REQUIRED** — always include at least one type label and one area label.
- `bin/ticket update <ticket-id> [OPTIONS]` - Update a ticket's status, title, description, labels, relations, project, parent, priority, or assignee.
- `bin/ticket close <ticket-id> [--cancel]` - Close a ticket (set status to Done or Canceled).
- `bin/ticket comment <ticket-id> "<message>"` - Add a comment to a ticket.
- `bin/ticket relate <ticket-id> [OPTIONS]` - Set up blocking relationships for a ticket. Supports multiple targets.
- `bin/ticket labels [--json]` - List all labels with their IDs.
- `bin/ticket projects [OPTIONS]` - List all projects.
- `bin/ticket project <create|get> "<name>" [OPTIONS]` - Create or get a project.
- `bin/ticket users [--json]` - List all users in the organization.
- `bin/ticket batch create --from <yaml-file> [--dry-run]` - Create multiple tickets from a YAML file.
- `bin/ticket batch assign-project --from <yaml-file> [--dry-run]` - Assign tickets to projects in bulk from a YAML file.
- `bin/ticket create-human-followup [--parent <ticket-id>] [--files <file>...]` - Create a HUMAN-labeled follow-up ticket for deployment infrastructure that requires human action.
- `bin/vibe pr` - Create a pull request for the current branch. PR titles must include the ticket reference.
- `bin/vibe figma analyze` - Analyze frontend codebase for design system context.
- `bin/vibe generate-agent-instructions` - Generate assistant-specific instruction files.
