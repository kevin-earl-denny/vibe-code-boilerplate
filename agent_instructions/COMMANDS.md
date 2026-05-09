# Agent Commands Reference

These commands are available to AI agents working on this project.

## Setup

### doctor
Check project health and configuration.
**Usage**: `bin/vibe doctor`
**Examples:**
- `bin/vibe doctor`
- `bin/vibe doctor --verbose`

### setup
Run the setup wizard to configure your project.
**Usage**: `bin/vibe setup`
**Examples:**
- `bin/vibe setup`
- `bin/vibe setup --force`
- `bin/vibe setup --wizard tracker`

## Ticket Operations

### do
Start working on a ticket (creates worktree and branch).
**Usage**: `bin/vibe do <ticket-id>`
**Examples:**
- `bin/vibe do PROJ-123`
- `bin/vibe do 45`

### ticket list
List tickets from the tracker.
**Usage**: `bin/ticket list [OPTIONS]`
**Options:**
- `--status, -s` — Filter by status (e.g. "In Progress", "Todo")
- `--label, -l` — Filter by label (repeatable)
- `--limit, -n` — Maximum tickets to show (default: 50)
- `--all` — Fetch all matching tickets (overrides --limit)
- `--project, -p` — Filter by project name
- `--parent` — Filter by parent ticket (show sub-tasks)
- `--priority` — Filter by priority (urgent, high, medium, low, none)
- `--assignee, -a` — Filter by assignee name (or "me")
- `--unassigned` — Show only unassigned tickets
**Examples:**
- `bin/ticket list`
- `bin/ticket list --status "In Progress"`
- `bin/ticket list --project "Q1 Roadmap"`
- `bin/ticket list --parent PROJ-100`
- `bin/ticket list --priority urgent`
- `bin/ticket list --assignee me`
- `bin/ticket list --unassigned`
- `bin/ticket list --all`

### ticket get
Get details for a specific ticket.
**Usage**: `bin/ticket get <ticket-id> [OPTIONS]`
**Options:**
- `--children, -c` — Include sub-tasks (children)
**Examples:**
- `bin/ticket get PROJ-123`
- `bin/ticket get PROJ-123 --children`

### ticket create
Create a new ticket. **A description is REQUIRED** — never create a ticket without one. **Labels are REQUIRED** — always include at least one type label and one area label.
**Usage**: `bin/ticket create "<title>" [OPTIONS]`
**Options:**
- `--description, -d` — Ticket description (required)
- `--label, -l` — Labels to add (repeatable)
- `--blocked-by` — Ticket IDs that block this ticket (repeatable)
- `--relates-to` — Related ticket IDs, non-hierarchical (repeatable)
- `--parent` — Parent ticket ID (creates as sub-task)
- `--project, -p` — Add to project (by name)
- `--priority` — Set priority (urgent, high, medium, low, none)
- `--assignee, -a` — Assign to user (name or "me")
- `--interactive, -i` — Interactive mode with guided prompts
- `--no-labels` — Explicitly skip label requirement
- `--dry-run` — Preview ticket without creating
**Examples:**
- `bin/ticket create "Add user authentication" --description "Add OAuth2 login flow." --label Feature --label Backend`
- `bin/ticket create "Fix login bug" --description "Login returns 500 on special chars." --label Bug --label "High Risk" --label Frontend`
- `bin/ticket create "Add signup form" --description "Create the signup form." --label Feature --label Frontend --parent PROJ-100`
- `bin/ticket create "Set up CI" --description "Add GitHub Actions." --label Chore --label Infra --priority high --assignee me`
- `bin/ticket create "Auth middleware" --description "Add JWT auth." --label Feature --label Backend --blocked-by PROJ-101`

### ticket update
Update a ticket's status, title, description, labels, relations, project, parent, priority, or assignee.
**Usage**: `bin/ticket update <ticket-id> [OPTIONS]`
**Options:**
- `--status, -s` — Set ticket status (e.g. "Done", "In Progress")
- `--title, -t` — Set ticket title
- `--description, -d` — Set ticket description
- `--label, -l` — Set labels (repeatable, replaces existing)
- `--blocked-by` — Add tickets that block this ticket (repeatable)
- `--blocks` — Add tickets that this ticket blocks (repeatable)
- `--project, -p` — Add to project (by name)
- `--remove-project` — Remove from current project
- `--parent` — Set parent ticket (make sub-task)
- `--no-parent` — Remove parent (make standalone)
- `--priority` — Set priority (urgent, high, medium, low, none)
- `--assignee, -a` — Assign to user (name or "me")
- `--unassign` — Remove assignee
**Examples:**
- `bin/ticket update PROJ-123 --status "In Progress"`
- `bin/ticket update PROJ-123 --title "New title" --description "Updated description"`
- `bin/ticket update PROJ-123 --label Feature --label Backend`
- `bin/ticket update PROJ-123 --blocked-by PROJ-100`
- `bin/ticket update PROJ-123 --blocks PROJ-456`
- `bin/ticket update PROJ-123 --project "Q1 Roadmap"`
- `bin/ticket update PROJ-123 --parent PROJ-100`
- `bin/ticket update PROJ-123 --no-parent`
- `bin/ticket update PROJ-123 --priority urgent --assignee me`

### ticket close
Close a ticket (set status to Done or Canceled).
**Usage**: `bin/ticket close <ticket-id> [--cancel]`
**Options:**
- `--cancel` — Mark as canceled instead of done
**Examples:**
- `bin/ticket close PROJ-123`
- `bin/ticket close PROJ-123 --cancel`

### ticket comment
Add a comment to a ticket.
**Usage**: `bin/ticket comment <ticket-id> "<message>"`
**Examples:**
- `bin/ticket comment PROJ-123 "PR opened, ready for review"`

### ticket relate
Set up blocking relationships for a ticket. Supports multiple targets.
**Usage**: `bin/ticket relate <ticket-id> [OPTIONS]`
**Options:**
- `--blocks` — Ticket IDs that this ticket blocks (repeatable)
- `--blocked-by` — Ticket IDs that block this ticket (repeatable)
**Examples:**
- `bin/ticket relate PROJ-101 --blocks PROJ-102`
- `bin/ticket relate PROJ-123 --blocks PROJ-456 PROJ-457 PROJ-458`
- `bin/ticket relate PROJ-123 --blocked-by PROJ-100`

### ticket labels
List all labels with their IDs.
**Usage**: `bin/ticket labels [--json]`
**Examples:**
- `bin/ticket labels`
- `bin/ticket labels --json`

### ticket projects
List all projects.
**Usage**: `bin/ticket projects [OPTIONS]`
**Options:**
- `--json` — Output as JSON
- `--state` — Filter by project state (planned, started, completed, canceled)
**Examples:**
- `bin/ticket projects`
- `bin/ticket projects --state started`
- `bin/ticket projects --json`

### ticket project
Create or get a project.
**Usage**: `bin/ticket project <create|get> "<name>" [OPTIONS]`
**Options (create):**
- `--description, -d` — Project description
- `--state` — Initial project state (planned, started, completed, canceled; default: planned)
**Examples:**
- `bin/ticket project create "Q1 Roadmap" --description "Q1 goals"`
- `bin/ticket project get "Q1 Roadmap"`

### ticket users
List all users in the organization.
**Usage**: `bin/ticket users [--json]`
**Examples:**
- `bin/ticket users`
- `bin/ticket users --json`

### ticket batch create
Create multiple tickets from a YAML file.
**Usage**: `bin/ticket batch create --from <yaml-file> [--dry-run]`
**Examples:**
- `bin/ticket batch create --from tickets.yaml`
- `bin/ticket batch create --from tickets.yaml --dry-run`

### ticket batch assign-project
Assign tickets to projects in bulk from a YAML file.
**Usage**: `bin/ticket batch assign-project --from <yaml-file> [--dry-run]`
**Examples:**
- `bin/ticket batch assign-project --from project-assignments.yaml`
- `bin/ticket batch assign-project --from project-assignments.yaml --dry-run`

### ticket create-human-followup
Create a HUMAN-labeled follow-up ticket for deployment infrastructure that requires human action.
**Usage**: `bin/ticket create-human-followup [--parent <ticket-id>] [--files <file>...]`
**Examples:**
- `bin/ticket create-human-followup`
- `bin/ticket create-human-followup --parent PROJ-123`
- `bin/ticket create-human-followup --parent PROJ-123 --files fly.toml --files vercel.json`

## Pull Requests

### pr
Create a pull request for the current branch. PR titles must include the ticket reference.
**Usage**: `bin/vibe pr`
**Examples:**
- `bin/vibe pr`
- `bin/vibe pr --title "PROJ-123: Add feature X"`
- `bin/vibe pr --web`

## Design

### figma analyze
Analyze frontend codebase for design system context.
**Usage**: `bin/vibe figma analyze`
**Examples:**
- `bin/vibe figma analyze`
- `bin/vibe figma analyze --figma-context`
- `bin/vibe figma analyze --json`

## Agent Instructions

### generate-agent-instructions
Generate assistant-specific instruction files.
**Usage**: `bin/vibe generate-agent-instructions`
**Examples:**
- `bin/vibe generate-agent-instructions`
- `bin/vibe generate-agent-instructions --format cursor`
- `bin/vibe generate-agent-instructions --dry-run`
