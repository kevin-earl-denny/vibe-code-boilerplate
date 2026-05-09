# Linear Projects

## When to Use This Recipe

Use this recipe when you need to:
- Organize tickets into Linear Projects for milestone or initiative tracking
- Use CLI commands to manage projects
- Set up conventions for how projects relate to labels and milestones
- Bulk-assign existing tickets to projects

## Prerequisites

- Linear tracker configured in `.vibe/config.json` (see `recipes/tickets/linear-setup.md`)
- `LINEAR_API_KEY` set in environment

---

## What Are Linear Projects?

Linear Projects group related tickets into a named initiative with a lifecycle state. They're useful for:

- **Milestones**: "Q1 Auth Overhaul", "V2 Launch"
- **Epics**: "Data Pipeline", "Payment Integration"
- **Workstreams**: "Backend API", "Mobile App"

Each project has a **state**: `planned`, `started`, `completed`, or `canceled`.

### Projects vs Labels vs Milestones

| Mechanism | Best For | Scope |
|-----------|----------|-------|
| **Projects** | Grouping tickets into initiatives with lifecycle tracking | Cross-cutting work spanning many tickets |
| **Milestone label** | Marking tickets as part of a larger feature | Lightweight tagging, no lifecycle |
| **Labels** | Type, risk, area classification | Per-ticket metadata |

**Recommendation:** Use Projects when you need lifecycle tracking (planned → started → completed). Use the Milestone label for lightweight grouping without state management.

---

## CLI Commands

### List projects

```bash
bin/ticket projects
bin/ticket projects --state started
bin/ticket projects --json
```

### Create a project

```bash
bin/ticket project create "Q1 Roadmap" --description "Q1 goals and deliverables"
bin/ticket project create "Backend API" --state started
```

### Get project details

```bash
bin/ticket project get "Q1 Roadmap"
```

### Assign a ticket to a project

```bash
# On creation
bin/ticket create "Add auth" --description "Add OAuth2 flow" --label Feature --label Backend --project "Q1 Roadmap"

# On update
bin/ticket update PROJ-123 --project "Q1 Roadmap"
```

### Remove a ticket from a project

```bash
bin/ticket update PROJ-123 --remove-project
```

### Filter tickets by project

```bash
bin/ticket list --project "Q1 Roadmap"
```

### Bulk assign tickets to projects

When bootstrapping projects on an existing board with many tickets:

> **Note:** This command assigns tickets to **existing** projects. Create the projects first with `bin/ticket project create "Name"` before running bulk assignment.

```bash
bin/ticket batch assign-project --from project-assignments.yaml
bin/ticket batch assign-project --from project-assignments.yaml --dry-run
```

YAML format:
```yaml
projects:
  - name: "Data Pipeline V1"
    tickets: [DEAL-4, DEAL-61, DEAL-62, DEAL-63]
  - name: "Backend API"
    tickets: [DEAL-83, DEAL-84, DEAL-85]
```

### Batch create with project assignment

The `batch create` command also supports project assignment per ticket:

```yaml
tickets:
  - title: "Set up auth"
    description: "Add JWT auth middleware"
    labels: [Feature, Backend, Medium Risk]
    project: "Q1 Roadmap"
```

---

## Organization Patterns

### Pattern 1: Feature-based projects

Group tickets by feature area. Each project represents a distinct feature or subsystem.

```
Project: "Authentication"     → login, logout, session, OAuth tickets
Project: "Reporting"          → dashboard, export, analytics tickets
Project: "Infrastructure"    → CI/CD, monitoring, deployment tickets
```

### Pattern 2: Release-based projects

Group tickets by release cycle or milestone.

```
Project: "V1.0 Launch"       → all tickets needed for initial launch
Project: "V1.1 Improvements" → post-launch enhancements
```

### Pattern 3: Hybrid

Use feature-based projects for ongoing work, release-based for time-bound goals.

---

## Conventions

1. **Name projects clearly** — Use descriptive names that convey scope (e.g., "Payment Integration V1" not "Payments")
2. **Update project state** — Move projects from `planned` → `started` → `completed` as work progresses
3. **Assign tickets at creation** — Use `--project` when creating tickets to keep projects current
4. **One project per ticket** — A ticket belongs to at most one project. If work spans projects, create separate tickets.
5. **Document projects in CLAUDE.md** — When projects are set up, add a table to the project's CLAUDE.md so agents know the project landscape

### Example CLAUDE.md Section

Add this to your project's CLAUDE.md after setting up Linear Projects:

```markdown
## Linear Projects

| Project | State | Description |
|---------|-------|-------------|
| Authentication | started | OAuth2, session management, MFA |
| Data Pipeline | planned | ETL, data validation, export |
| Infrastructure | started | CI/CD, monitoring, deployment |

When creating tickets, assign to the appropriate project with `--project "Name"`.
```

---

## See Also

- `recipes/tickets/creating-tickets.md` — Ticket creation checklist
- `recipes/tickets/linear-setup.md` — Initial Linear configuration
- `recipes/tickets/linear-github-integration.md` — Linear + GitHub sync
