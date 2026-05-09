# Creating Tickets

## When to Use This Recipe

Use this recipe when you need to:
- Create tickets programmatically (e.g., as an AI agent or via CLI)
- Set up blocking/blocked-by relationships between tickets
- Apply the correct labels so tickets match project conventions
- Group work with milestones or the Milestone label

## Prerequisites

- Tracker (Linear or Shortcut) configured in `.vibe/config.json`
- Labels defined in config exist in the tracker (see `recipes/tickets/linear-setup.md` or `recipes/tickets/shortcut.md`)

---

## 1. Blocking Relationships (Direction Matters)

**Terminology:**
- **"A blocks B"** → B cannot start until A is done. (A is the prerequisite.)
- **"A is blocked by B"** → A cannot start until B is done. (B is the prerequisite.)

When creating a dependency between tickets, the **foundation/prerequisite ticket blocks the dependent ticket**, not the other way around.

### Correct

| Situation | Relationship to create |
|-----------|-------------------------|
| "Set up React app" depends on "Initialize monorepo" | **Initialize monorepo** BLOCKS **Set up React app** |
| "Configure CI" depends on "Initialize monorepo" | **Initialize monorepo** BLOCKS **Configure CI** |

**CORRECT:** "Initialize monorepo" BLOCKS "Set up React app"  
(React app depends on monorepo being done first.)

### Wrong

**WRONG:** "Initialize monorepo" BLOCKED BY "Set up React app"  
(That would mean monorepo can't start until React is done — backwards.)

### Checklist When Linking Tickets

1. Identify which ticket is the **prerequisite** (must be done first).
2. In the tracker, set: **prerequisite ticket blocks dependent ticket(s)**.
3. Do **not** set the foundation ticket as "blocked by" the later tickets.

---

## 2. Label Checklist (Required When Creating Tickets)

Every ticket you create must have labels from `.vibe/config.json`. Apply all three categories:

### Type (exactly one)

| Label | Use When |
|-------|----------|
| **Bug** | Fixing broken functionality |
| **Feature** | New functionality |
| **Chore** | Maintenance, dependencies, cleanup |
| **Refactor** | Code improvement, no behavior change |

### Risk (exactly one)

| Label | Criteria |
|-------|----------|
| **Low Risk** | Docs, tests, typos, minor UI tweaks |
| **Medium Risk** | New features, bug fixes, refactoring |
| **High Risk** | Auth, payments, database, infrastructure |

### Area (at least one; use all that apply)

| Label | Scope |
|-------|--------|
| **Frontend** | UI, client-side code |
| **Backend** | Server, API, business logic |
| **Infra** | DevOps, CI/CD, infrastructure |
| **Docs** | Documentation only |

### Special (optional)

- **HUMAN** – Requires human decision/action; stop and hand off.
- **Milestone** – Part of a larger feature (see Milestones below).
- **Blocked** – Waiting on an external dependency.

### Agent Checklist

When creating a ticket, before saving:

- [ ] Type label assigned (Bug / Feature / Chore / Refactor)
- [ ] Risk label assigned (Low Risk / Medium Risk / High Risk)
- [ ] Area label(s) assigned (Frontend / Backend / Infra / Docs)
- [ ] Blocking relationships point the right way (prerequisite blocks dependent)
- [ ] **Priority (Linear only):** If the ticket has a priority, set the **Priority field** (not a label). See [Priority field](#5-priority-field-linear) below.
- [ ] **Project (if applicable):** If Linear Projects are set up, assign the ticket to the appropriate project with `--project "Name"`. See `recipes/tickets/linear-projects.md`.

---

## 3. Milestones

Two approaches; use the one that fits your tracker and workflow.

### Option A: "Milestone" Label + Ticket Linking (Recommended)

- Use the **Milestone** label on tickets that are part of a larger feature.
- Link related tickets (e.g., parent/child or blocks/blocked-by) so the group is clear.
- Keeps the model "1 ticket = 1 PR" and works the same across Linear and Shortcut.

**Example:** "Auth epic" is represented by tickets PROJ-10 (Add login), PROJ-11 (Add logout), PROJ-12 (Session refresh). All three get the **Milestone** label and are linked to a parent or to each other as needed.

### Option B: Native Milestones (Linear/Shortcut)

- Create a milestone in the tracker (e.g., "Q1 Auth").
- Assign tickets to that milestone via the tracker UI or API.
- Use when the team already uses native milestones for planning.

**Recommendation:** Prefer Option A unless the project has already standardized on native milestones. Option A is simpler and consistent across trackers.

---

## 4. Title and Content

- **Title:** Use "Verb + Object" (e.g., "Add login form", "Fix null pointer in auth").
- **Description:** Include acceptance criteria and any context.
- **Links:** Add related tickets (blocks/blocked-by, parent/child) with correct direction.

---

## 5. Priority Field (Linear)

**Use Linear’s Priority field, not labels.** Do not create or use P0, P1, P2, or P3 as labels.

When creating or editing a ticket in Linear, set the **Priority** field to one of: **Urgent**, **High**, **Medium**, **Low**, **No Priority**. Map common shorthand as follows:

| Shorthand | Set Priority field to |
|-----------|------------------------|
| P0 / critical | Urgent |
| P1 / high | High |
| P2 / medium | Medium |
| P3 / low | Low |
| (none) | No Priority |

If you use the Linear API to create issues, pass `priority` in the issue input (e.g. `priority: 1` for Urgent, per Linear’s schema). In the Linear UI, use the priority dropdown on the ticket.

---

## Quick Reference

| Do | Don't |
|----|--------|
| Prerequisite ticket **blocks** dependent ticket | Foundation ticket "blocked by" later tickets |
| Assign type + risk + area on every ticket | Leave type/risk/area unset |
| Set **Priority field** in Linear (Urgent/High/Medium/Low) | Use P0/P1/P2/P3 as **labels** |
| Use "Milestone" label for epic-style work | Rely only on priority labels without type/risk/area |
| Verb + Object titles | Vague titles like "Fix stuff" |
| Assign to a project when projects are set up | Leave tickets unassigned to a project |

See also: `CLAUDE.md` (Ticket Management, Creating Tickets, Label Documentation), `recipes/tickets/linear-setup.md`, `recipes/tickets/shortcut.md`, `recipes/tickets/linear-projects.md`.
