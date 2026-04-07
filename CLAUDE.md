# CLAUDE.md – AI Agent Instructions

**Filename:** This file must be named **CLAUDE.md** (all caps) in the project root so Cursor and other tools load it as the project’s agent instructions.

This file contains instructions for AI agents (Claude, GPT, etc.) working on projects that use this boilerplate.

---

## Project Overview

**Fill this in after applying the boilerplate** so AI agents have immediate context on what the project is. Run `bin/vibe setup` when ready; consider updating this section as part of that flow.

- **What this project does:** *(e.g. "SaaS dashboard for inventory and orders")*
- **Tech stack:** *(e.g. backend: Django; frontend: React; database: PostgreSQL; deployment: Fly.io)*
- **Key features / domains:** *(e.g. auth, reporting, webhooks)*
- **Specs or docs:** *(link to ADRs, product spec, or "None yet" if they don't exist)*

---

## Language-Agnostic Tooling

**This boilerplate works with any programming language.** The CLI tools (`bin/vibe`, `bin/ticket`) are written in Python, but they're workflow automation that runs **alongside** your project, not part of it.

**If the project uses JavaScript, Go, Rust, Ruby, or any other language:**
- The Python tooling is for workflow automation only (tickets, worktrees, PR policies)
- No Python dependencies are added to your project's package.json, Cargo.toml, go.mod, etc.
- Your app's build, test, and deploy processes are unchanged
- When writing code, use the project's actual language and frameworks

**Example:** A Next.js project using this boilerplate:
- App code: TypeScript/React
- Tests: Jest or Vitest
- Build: `npm run build`
- Workflow tooling: `bin/vibe do PROJ-123` (Python, but doesn't affect your app)

---

## Multi-Assistant Support

This boilerplate supports multiple AI coding assistants. A single source of truth in `agent_instructions/` generates format-specific files for:

| Assistant | File Generated |
|-----------|----------------|
| Claude Code | `CLAUDE.md` |
| Cursor IDE | `.cursor/rules` |
| GitHub Copilot | `.github/copilot-instructions.md` |

### Maintaining Instructions

Edit the source files in `agent_instructions/`:
- `CORE.md` - Project context and core rules
- `COMMANDS.md` - Available commands
- `WORKFLOW.md` - Standard workflows

Then regenerate assistant files:

```bash
bin/vibe generate-agent-instructions
```

### Source File Format

The source files use simple markdown:

```markdown
# CORE.md
## Project Overview
- **Name**: My Project
- **Description**: What it does

## Core Rules
- Read files before modifying
- Use existing patterns

## Anti-Patterns
- Guessing file contents
- Over-engineering
```

See `agent_instructions/` for the full template.

---

## Before You Build: Validate Your Idea

**For vibe coders who prompt faster than they think.** Before investing time building something, use `/assess` to validate that it's worth building.

### When to Use `/assess`

| Situation | Use `/assess`? |
|-----------|---------------|
| Starting a new app or significant feature | **Yes** |
| Building something that might already exist | **Yes** |
| Pivoting an existing project | **Yes** |
| Learning project / tutorial | Optional |
| Bug fix or small improvement | No |
| Client project with defined requirements | No |

### What `/assess` Does

1. **Understands your idea** through interactive Q&A
2. **Researches competitors** via web search (with your consent)
3. **Identifies market gaps** you could fill
4. **Challenges your assumptions** with hard questions
5. **Recommends**: Proceed / Reconsider / Pivot

### Example

```
You: I want to build an AI-powered todo app

/assess

[Interactive session: questions about problem, users, differentiation]
[Web research: finds Todoist AI, Motion, Reclaim.ai, etc.]
[Analysis: existing solutions are mature, market is crowded]

Recommendation: RECONSIDER
- Todoist already has AI prioritization
- Motion does AI scheduling well
- Consider: What's your 10x differentiator?
- Alternative: Build a plugin for existing tool instead?
```

### Works on Existing Projects

Running `/assess` on an existing project will:
- Read your codebase to understand what you've built
- Check if the competitive landscape has changed
- Help you decide: double down, pivot, or sunset

---

## README Maintenance

Keep the project **README.md** accurate so humans and agents can onboard quickly.

### When a new app is initialized (from a prompt or setup)

After creating or configuring a new project, update **README.md** with:

- **App name and description** – What the project does and who it’s for
- **Tech stack** – Frameworks, runtimes, databases, deployment (align with Project Overview in this file)
- **Setup instructions** – Prerequisites, install steps, env vars, how to run locally
- **Project structure** – Short overview of key directories (e.g. `api/`, `ui/`, `scripts/`)

If the user ran `bin/vibe setup`, remind them to update README as part of the “next steps” (see setup wizard).

### Continuous maintenance

As the project evolves, keep README in sync:

- **New features** – Document user-facing or notable capabilities
- **Setup steps** – Refine when install/run steps change
- **Architecture changes** – Update structure or diagrams when layout or responsibilities change

When you add a new top-level area (e.g. a new app, service, or major script), add a brief note to README and to the Project Overview above.

See `recipes/agents/readme-maintenance.md` for the full guide.

---

## Configuration Reference

The canonical configuration is in `.vibe/config.json`. Key fields are populated when you run `bin/vibe setup` (tracker, `github.owner`, `github.repo`, etc.). Example shape:

```json
{
 "tracker": { "type": "linear", "config": { "deployed_state": "Deployed" } },
 "github": { "auth_method": "gh_cli", "owner": "<your-org>", "repo": "<your-repo>" },
 "branching": { "pattern": "{PROJ}-{num}", "always_rebase": true },
 "labels": {
 "type": ["Bug", "Feature", "Chore", "Refactor"],
 "risk": ["Low Risk", "Medium Risk", "High Risk"],
 "area": ["Frontend", "Backend", "Infra", "Docs"],
 "special": ["HUMAN", "Milestone", "Blocked"]
 }
}
```

- **tracker.config.github_integration** (optional): `"native"` or `"fallback"`. Set during setup wizard.
  - `"native"` (recommended): Use Linear's native GitHub integration. The fallback workflows are not needed.
  - `"fallback"`: Use custom GitHub Actions workflows (`pr-opened.yml`, `pr-merged.yml`).
- **tracker.config.deployed_state** (optional): State name to use when a PR is merged (e.g. `Deployed`, `Done`, `Released`). Only used with fallback workflows.
- **tracker.config.in_review_state** (optional): State name when a PR is opened (default: `In Review`). Only used with fallback workflows.
- **tracker.config.done_state** (optional): Final "done" state name (e.g. `Done`, `Closed`). Used when UAT workflow is enabled—tickets go to `deployed_state` (e.g. `To Test`) on merge, then manually to `done_state` after verification. See `recipes/workflows/uat-testing.md`.

### Context Loading: Native vs Fallback Workflows

**IMPORTANT for AI agents:** Before referencing the fallback PR workflows, check the configuration:

```bash
# Check github_integration setting
cat .vibe/config.json | grep github_integration
```

- If `github_integration: "native"` → **Do NOT reference** `pr-opened.yml`, `pr-merged.yml`, or the fallback workflow recipes. These are not in use.
- If `github_integration: "fallback"` or not set → The fallback workflows are active and relevant.

This prevents loading unnecessary context about workflows that aren't being used.

---

## LLM-Powered Applications

When building applications that make API calls to LLMs (OpenAI, Anthropic, etc.), use **PromptVault** for prompt management.

### When to Use PromptVault

**Use PromptVault when the application:**
- Has prompts that will evolve over time
- Shares context or instructions across multiple prompts
- Needs version control for prompts
- Separates prompt engineering from code

**Skip PromptVault for:**
- One-off scripts or experiments
- Prompts that never change
- Applications without LLM API calls

### Quick Setup

```bash
# During initial setup
bin/vibe setup   # Select "Yes" for PromptVault when prompted
```

> **Note:** There is no `--wizard promptvault` option yet. Configure PromptVault during initial `bin/vibe setup`.

### Usage Pattern

Instead of hardcoding prompts:

```python
# DON'T do this
prompt = "You are a helpful assistant for {company}. Help with: {query}"
```

Use PromptVault:

```python
# DO this
from your_app.prompts import get_compiled_prompt

prompt = get_compiled_prompt("customer-support", {
    "company": company_name,
    "query": user_query
})
```

See `recipes/integrations/promptvault.md` for full documentation and the `/promptvault` skill for scaffolding.

---

## Agent Commands Quick Reference

**Use these blessed commands.** They handle edge cases, update state correctly, and follow project conventions.

### Essential Commands

| Command | When to Use | What It Does |
|---------|-------------|--------------|
| `bin/vibe do PROJ-123` | Starting work on a ticket | Creates worktree from latest main, sets up branch |
| `bin/vibe pr` | Done with feature | Opens PR with template, from worktree |
| `bin/vibe doctor` | After any git/worktree changes | Validates setup, syncs state |
| `bin/vibe setup --quick` | New project setup | Sensible defaults, no prompts |

### Ticket Operations

| Command | When to Use |
|---------|-------------|
| `bin/ticket list` | See available tickets |
| `bin/ticket get PROJ-123` | Get ticket details before starting |
| `bin/ticket create "Title"` | Create new ticket |
| `bin/ticket update PROJ-123 --status "In Progress"` | Update ticket status |

### Debugging

| Command | When to Use |
|---------|-------------|
| `bin/vibe cors-check <url>` | Diagnosing CORS errors |
| `bin/vibe retrofit --analyze-only` | See what retrofit would change |
| `bin/vibe init-actions --dry-run` | Preview GitHub Actions setup |

### Integration Setup

| Command | What It Configures |
|---------|-------------------|
| `bin/vibe setup -w tracker` | Linear/Shortcut |
| `bin/vibe setup -w vercel` | Vercel deployment |
| `bin/vibe setup -w fly` | Fly.io deployment |
| `bin/vibe setup -w supabase` | Supabase database |
| `bin/vibe setup -w sentry` | Sentry error monitoring |
| `bin/vibe init-actions` | GitHub Actions workflows |

### Worktree Cleanup

After PR is merged:
```bash
git worktree remove ../project-worktrees/PROJ-123
git branch -d PROJ-123
bin/vibe doctor
```

---

## Core Rules

### When to Ask for Clarification

**Always ask when:**
- Requirements are ambiguous or contradictory
- Multiple valid implementations exist with different trade-offs
- Security or data implications are unclear
- The task would take significant time if the wrong approach is chosen
- Destructive operations are involved

**Never ask when:**
- The answer is clearly in the codebase
- Standard patterns apply
- It's a trivial decision with easy reversal
- The question was already answered in context

See `recipes/agents/asking-clarifying-questions.md` for examples.

### When to Create HUMAN Tickets

The `HUMAN` label means "I cannot proceed without human action." Use it sparingly.

**DO create HUMAN tickets for:**
- Obtaining **actual secret values** (API keys, passwords the human must retrieve)
- External account actions (creating accounts on third-party services, enabling billing)
- Subjective decisions (UI/UX choices, branding, product direction)
- Legal/compliance review
- External communications (emails to users, public announcements)

**DO NOT create HUMAN tickets for:**
- Writing code or config files (even security-related code)
- Running CLI commands (`fly secrets set`, `gh secret set`, etc.)
- Setting up infrastructure (Dockerfiles, workflows, terraform)
- Documentation
- Architecture decisions (if requirements are clear, just implement)
- Installing dependencies or tools

**Ask yourself:** "Can I do this programmatically?" If yes, do it. If no, create a HUMAN ticket.

**Example:**
- "Provide DATABASE_URL" → HUMAN (need actual credential value)
- "Configure Fly.io secrets" → NOT HUMAN (you can run `fly secrets set`)
- "Write RLS policies" → NOT HUMAN (you can write the code)

See `recipes/agents/human-required-work.md` for the full guide.

### How to Handle Ambiguity

1. **Check context first** - Re-read the request, examine related code
2. **Make informed assumptions** - If confidence >80%, proceed with a note
3. **Ask with options** - Provide 2-3 specific options, not open-ended questions
4. **Document assumptions** - Note any assumptions in code comments or PR description

### File Editing

**No files in this repo are protected.** You may edit any file freely. Do not treat any path as read-only or off-limits; apply changes wherever they are needed to complete the task.

### Efficient Command Execution

**Prefer absolute paths and command-specific directory flags over `cd path && command`.** The latter causes sequential execution, resets shell working directory between commands, and adds unnecessary overhead.

| Avoid | Prefer |
|-------|--------|
| `cd /path && git status` | `git -C /path status` |
| `cd /path && git add . && git commit -m "..."` | `git -C /path add .` then `git -C /path commit -m "..."` (or one invocation with multiple args) |
| `cd /path && git push -u origin BRANCH` | `git -C /path push -u origin BRANCH` |
| `cd /path && npm install` | `npm --prefix /path install` |
| `cd /path && npm run build` | `npm --prefix /path run build` |
| `cd /path && gh pr create ...` | `gh pr create --repo owner/repo ...` (repo from main checkout or config; use `--head branch` if needed) |

**Worktree workflows:** When operating on a worktree (e.g. `../project-worktrees/PROJ-123`), use `git -C <worktree-path> ...` for all git commands from the main repo or from another shell. Use `gh pr create --repo owner/repo --head PROJ-123 ...` so you don't need to `cd` into the worktree to open the PR. This allows parallel or independent commands without changing directory.

---

## Ticket Management

### "Do this ticket {ticket}" – What it means

When the user says **"do this ticket PROJ-123"** (or any ticket ID), that means:

1. **Do the work on a fresh worktree** – Create a dedicated worktree for that ticket (`bin/vibe do PROJ-123`), do all work there (no work in the main checkout).
2. **Open a PR when complete** – When the work is done, commit, push, and open a PR (title with ticket ref, risk label, etc.). Do not leave the work only local.

So: **"do this ticket {ticket}"** = **do this ticket on a fresh worktree and open a PR when complete.**

### Ticketing System (Linear) Must Be Configured First

A tracker must be configured in `.vibe/config.json` before ticket commands work. If no tracker is configured, the CLI will prompt to run setup. Ensure the project has run `bin/vibe setup` (or `bin/vibe setup --wizard tracker`) before using ticket commands.

### Starting Work on a Ticket

When asked to "do" a ticket, use a fresh worktree and open a PR when done (see ["Do this ticket"](#do-this-ticket--ticket--what-it-means) above).

```bash
# Use the vibe CLI to create a worktree
bin/vibe do PROJ-123
```

This creates:
- A worktree at `../project-worktrees/PROJ-123/`
- A branch named according to the pattern (e.g., `PROJ-123`)

### Creating Tickets

When creating tickets programmatically:
1. **Check for duplicates first** — Search existing tickets (open and recently closed) for similar work before creating a new ticket. If a ticket already covers the same scope, update that ticket instead.
2. Use descriptive titles: "Verb + Object" format
3. **Apply labels** (see [Label checklist](#label-checklist-for-ticket-creation) below)
4. Include acceptance criteria
5. Link related tickets with **correct blocking direction** (see [Blocking relationships](#blocking-relationships) below)
6. **Assign to a project** (if Linear Projects are set up) with `--project "Name"`. See `recipes/tickets/linear-projects.md`.

#### Avoiding Duplicate Tickets

Before creating a ticket, run `bin/ticket list` and check for existing tickets covering the same scope. If a duplicate exists, update it instead of creating a new one. If scopes overlap but differ, document the boundary in both and link with "related to".

#### Blocking relationships

Direction matters: the **prerequisite** ticket **blocks** the dependent ticket, not the other way around.

- **"A blocks B"** = B cannot start until A is done. Set the foundation ticket as blocking the dependent one.
- Use blocking only for true code dependencies, HUMAN prerequisites, or sequential deployments — not for parallel work or ordering preferences.
- **Keep the dependency graph shallow.** If you have A → B → C → D, consider if B and C can be parallel.

See `recipes/tickets/creating-tickets.md` for full guidance and examples.

#### Label checklist for ticket creation

When creating a ticket, assign:

- **Type** (exactly one): Bug, Feature, Chore, Refactor
- **Risk** (exactly one): Low Risk, Medium Risk, High Risk
- **Area** (at least one): Frontend, Backend, Infra, Docs

Optional: **HUMAN**, **Milestone**, **Blocked** (see [Special Labels](#special-labels)).

#### Priority (Linear): use the Priority field, not labels

**Do not use P0, P1, P2, or P3 as labels.** Linear has a native **Priority** field. Set priority via that field so it works with Linear’s priority views and filters.

When creating or updating tickets, set the **Priority** field (not a label) using this mapping:

| If you mean | Set Linear Priority to |
|-------------|-------------------------|
| P0 / critical | **Urgent** |
| P1 / high | **High** |
| P2 / medium | **Medium** |
| P3 / low | **Low** |
| No priority | **No Priority** |

Labels in `.vibe/config.json` are for **type**, **risk**, and **area** only. Do not add P0/P1/P2/P3 to the label config.

### Ticket Status Updates

Update ticket status as work progresses:
- **Todo** → **In Progress**: When starting work
- **In Progress** → **In Review**: When PR is opened
- **In Review** → **Done**: When PR is merged

### Finding Actionable Tickets

When asked to "find unblocked tickets" or "look for work to do":

1. **Check open PRs** — `gh pr list --repo <owner>/<repo>`. Tickets with open PRs are already in flight; exclude them.
2. **Filter candidates** — `bin/ticket list --status "Todo,Backlog"`. Exclude Done/Deployed/Canceled, HUMAN-labeled, and blocked tickets.
3. **Validate each candidate** — Fetch details. Fix hygiene issues: add missing blocking relationships, cancel completed/stale tickets, add missing HUMAN labels.
4. **Pick highest-priority** — Milestone priority first, then ticket number (lower first), then foundation work before dependents, then lower risk for quick wins.

Produce a short triage report listing: actionable tickets, issues fixed during triage, and still-blocked tickets with a recommendation.

### HUMAN Follow-Up for Deployment Infrastructure

When a deployment infrastructure ticket is completed (e.g. added `fly.toml`, `vercel.json`, `.env.example`), create a **HUMAN-labeled follow-up ticket** so a human can set up production accounts and deploy. Use:

- **Manual:** `bin/ticket create-human-followup` (optionally `--parent PROJ-123` or `--files fly.toml --files vercel.json`)
- **Auto:** The workflow `.github/workflows/human-followup-on-deployment.yml` creates the ticket on merge to main when deployment config files were added (requires repo secrets `LINEAR_API_KEY`, `LINEAR_TEAM_ID`)

See `recipes/tickets/human-followup-deployment.md` for full guidance.

---

## Worktree Management

**Agent rule:** When the user asks to clean up worktrees, branches, or "tidy up" local state, follow the cleanup order below. Do not skip steps.

- **Create:** `bin/vibe do PROJ-123` creates a worktree and branch for that ticket.
- **Clean up when:** PR is merged, branch is no longer needed, or user asks to "tidy up".
- **Do not remove** a worktree while the branch is still in use (open PR, WIP).

### Cleaning Up Worktrees — Follow This Order

1. `git worktree remove <path-to-worktree>` (from **main** repo, not from inside the worktree; use `--force` if needed)
2. `git branch -d PROJ-123` (use `-D` if git reports "not fully merged")
3. `bin/vibe doctor` (syncs `.vibe/local_state.json`)

For bulk cleanup: run `git worktree list`, remove each non-main worktree, delete obsolete branches, then `bin/vibe doctor`.

See `recipes/workflows/git-worktrees.md` for full details on worktree setup, directory structure, and best practices.

### Avoiding Duplicate PRs (Multiple Worktree Systems)

**Risk:** Claude Code's `isolation: "worktree"` setting and `bin/vibe do` both create worktrees, but they use **different branch naming conventions** and are unaware of each other. If both are used for the same ticket, two branches — and two PRs — get created for the same work.

**Rules:**
- **Do not** use `isolation: "worktree"` (in `.claude/settings.json`) alongside `bin/vibe do` for the **same ticket**. Pick one system per ticket.
- `bin/vibe pr` will automatically check for existing PRs referencing the same ticket ID before creating a new one. If a duplicate is detected, it warns and asks for confirmation.
- `bin/vibe do` records the ticket-to-branch mapping in `.vibe/local_state.json`. The `pr` command checks this state to detect when a second branch exists for the same ticket.

**If you see a duplicate-PR warning**, stop and check whether the existing PR already covers the work. If it does, discard the current branch. If the new branch contains different/additional changes, coordinate manually (e.g. close the old PR or rebase onto the existing branch).

---

## Multi-Agent Coordination

When multiple AI agents work on the same codebase, follow these rules:

1. **Use worktree isolation** - Each agent MUST use its own worktree (`bin/vibe do PROJ-123`)
2. **Check what's in flight** - Run `git fetch --all && git branch -r` before starting
3. **Avoid high-risk files** - `CLAUDE.md`, `package.json`, migrations are conflict-prone
4. **Coordinate via tracker** - Keep tickets "In Progress" so others see claimed work

See `recipes/workflows/multi-agent-coordination.md` for full details on situational awareness, conflict prevention, and communication signals.

---

## PR Opening Checklist

Before opening a PR, ensure:

### Required
- [ ] Branch follows naming convention (`{PROJ}-{num}`)
- [ ] Rebased onto latest main (`git rebase origin/main`)
- [ ] All tests pass locally (if tests exist)
- [ ] PR title includes ticket reference
- [ ] Risk label selected (Low/Medium/High Risk)

### Recommended
- [ ] PR description uses template
- [ ] Testing instructions included (for non-trivial changes)
- [ ] Screenshots included (for UI changes)
- [ ] Documentation updated (if behavior changes)

### PR Template Location
`.github/PULL_REQUEST_TEMPLATE.md`

---

## Label Documentation

### Type Labels
| Label | Use When |
|-------|----------|
| **Bug** | Fixing broken functionality |
| **Feature** | Adding new functionality |
| **Chore** | Maintenance, dependencies, cleanup |
| **Refactor** | Code improvement, no behavior change |

### Risk Labels
| Label | Criteria |
|-------|----------|
| **Low Risk** | Docs, tests, typos, minor UI tweaks |
| **Medium Risk** | New features (flagged), bug fixes, refactoring |
| **High Risk** | Auth, payments, database, infrastructure |

### Area Labels
| Label | Scope |
|-------|-------|
| **Frontend** | UI, client-side code |
| **Backend** | Server, API, business logic |
| **Infra** | DevOps, CI/CD, infrastructure |
| **Docs** | Documentation only |

### Special Labels
| Label | Purpose |
|-------|---------|
| **HUMAN** | Requires human decision/action |
| **Milestone** | Part of a larger feature |
| **Blocked** | Waiting on external dependency |

### Milestones

- **Option A (recommended):** Use the **Milestone** label on tickets that are part of a larger feature, and link related tickets (blocks/blocked-by or parent/child). Keeps 1 ticket = 1 PR and works across trackers.
- **Option B:** Use Linear/Shortcut native milestones when the team already plans with them.

See `recipes/tickets/creating-tickets.md` for details.

---

## GitHub Actions Results

### Understanding CI Failures

**Always read the actual failure first.** Do not guess from workflow names.

1. **PR comments** – CodeQL and checks post inline comments. Read the exact finding, file, and line.
2. **Failed run logs** – `gh pr checks <number>` then `gh run view <run-id> --log-failed`.
3. **PR policy bot** – Lists missing items (ticket reference, risk label, etc.).

### Workflow Reference

| Workflow | Common Failures |
|----------|----------------|
| **security.yml** | Gitleaks (secret in code), dependency review, CodeQL findings |
| **pr-policy.yml** | Missing ticket reference, risk label, or branch naming |
| **pr-opened.yml** | Fallback Linear integration (not needed with native integration). See `recipes/tickets/linear-github-integration.md` |
| **pr-merged.yml** | Fallback Linear integration (not needed with native integration). See `recipes/tickets/linear-github-integration.md` |
| **tests.yml** | Test failure or no tests detected |

### Responding to CI Failures

- **Secret detected:** Remove from code, add to `.vibe/secrets.allowlist.json` if intentional, rotate the secret.
- **Missing labels:** `gh pr edit` to add the required label.
- **CodeQL findings:** Read the inline PR comment, fix or add documented suppression, push.
- **Test failures:** Read failure output, fix the test or code, push.

---

## Recipes Reference

Browse `recipes/` for the full collection. Key recipes:

- `recipes/workflows/git-worktrees.md` — Parallel development
- `recipes/workflows/branching-and-rebasing.md` — Git workflow
- `recipes/workflows/multi-agent-coordination.md` — Multi-agent conflict prevention
- `recipes/workflows/pr-risk-assessment.md` — Risk classification
- `recipes/agents/sub-agent-patterns.md` — Sub-agent task decomposition
- `recipes/agents/asking-clarifying-questions.md` — When to ask vs proceed
- `recipes/agents/human-required-work.md` — HUMAN tickets
- `recipes/agents/readme-maintenance.md` — README upkeep
- `recipes/security/secret-management.md` — Secrets
- `recipes/security/permissions-hardening.md` — GitHub Actions security
- `recipes/architecture/adr-guide.md` — Decision records
- `recipes/tickets/creating-tickets.md` — Ticket best practices
- `recipes/tickets/linear-github-integration.md` — Linear + GitHub
- `recipes/tickets/linear-projects.md` — Linear Projects management
- `recipes/testing/playwright.md` — E2E testing
- `recipes/testing/vitest.md` — Unit testing
- `recipes/debugging/cors-errors.md` — CORS diagnosis
- `recipes/integrations/promptvault.md` — LLM prompt management
- `recipes/integrations/sentry.md` — Error monitoring
- `recipes/integrations/neon.md` — Neon Postgres
- `recipes/deployment/fly-io.md` — Fly.io deployment
- `recipes/deployment/vercel.md` — Vercel deployment
- `recipes/databases/supabase.md` — Supabase
- `recipes/databases/neon.md` — Neon branching
- `recipes/databases/byo-postgres.md` — BYO Postgres
- `recipes/design/figma-to-code.md` — Design to implementation

---

## Skills Reference

Use these slash commands for common workflows:

| Skill | Description |
|-------|-------------|
| `/assess` | **Business validation** - Research competitors and validate your idea before building |
| `/setup` | Run the initial project setup wizard |
| `/do PROJ-123` | Start working on a ticket (creates worktree) |
| `/pr` | Create a pull request for the current branch |
| `/doctor` | Check project health and configuration |
| `/ticket list` | List tickets from the tracker |
| `/ticket get PROJ-123` | Get ticket details |
| `/ticket create "Title"` | Create a new ticket |
| `/cleanup` | Clean up merged worktrees |
| `/promptvault` | Manage PromptVault prompts, snippets, and variables |
| `/vercel` | Deploy and manage Vercel projects |
| `/fly` | Deploy and manage Fly.io applications |
| `/supabase` | Manage Supabase database, auth, and local development |
| `/sentry` | Configure Sentry error monitoring and releases |
| `/neon` | Manage Neon serverless Postgres and database branches |
| `/figma` | Design-to-code workflow: analyze codebase, generate Figma AI prompts, create tickets |

Skills are defined in `.claude/commands/` and can be customized per project.

---

## CLI Reference

These are the underlying CLI commands (skills call these automatically):

```bash
# Setup and health
bin/vibe setup              # Initial configuration
bin/vibe retrofit           # Apply boilerplate to existing project
bin/vibe retrofit --analyze-only  # See what retrofit would change
bin/vibe setup --wizard vercel     # Configure Vercel deployment
bin/vibe setup --wizard fly        # Configure Fly.io deployment
bin/vibe setup --wizard supabase   # Configure Supabase database
bin/vibe setup --wizard sentry     # Configure Sentry error monitoring
bin/vibe setup --wizard neon       # Configure Neon serverless Postgres
bin/vibe setup --wizard playwright # Configure Playwright E2E testing
bin/vibe doctor             # Health check
bin/doctor                  # Alias for doctor

# Ticket operations
bin/ticket list             # List tickets
bin/ticket get PROJ-123     # Get ticket details
bin/ticket create "Title"   # Create ticket
bin/ticket labels           # List label IDs
bin/ticket create-human-followup   # Create HUMAN follow-up for deployment

# Working on tickets
bin/vibe do PROJ-123        # Create worktree for ticket

# Secrets
bin/secrets list            # List secrets
bin/secrets sync            # Sync to provider

# Multi-assistant support
bin/vibe generate-agent-instructions  # Generate instruction files for all assistants
bin/vibe generate-agent-instructions --format cursor  # Generate for specific format
bin/vibe generate-agent-instructions --dry-run  # Preview without writing

# Design-to-code workflow
bin/vibe figma analyze      # Analyze frontend (frameworks, tokens, components)
bin/vibe figma analyze --figma-context  # Output context for Figma AI prompts
bin/vibe figma analyze --json  # JSON output for scripting
bin/vibe figma prompt       # Generate optimized Figma AI prompt
bin/vibe figma tickets      # Break design into implementation tickets
```

---

## Common Patterns

### Starting a New Feature

```bash
bin/ticket get PROJ-123                    # 1. Get ticket details
bin/vibe do PROJ-123                       # 2. Create worktree
# ... implement feature in worktree ...
git -C "$WORKTREE" add . && git -C "$WORKTREE" commit -m "PROJ-123: Add feature"
git -C "$WORKTREE" push -u origin PROJ-123
gh pr create --repo owner/repo --head PROJ-123 --title "PROJ-123: Add feature" --body "..."
```

### Handling CI Failures

Read the actual failure first (`gh pr checks <number>`, then `gh run view <run-id> --log-failed`). Check PR comments for CodeQL/policy bot findings. Fix and push.

---

## Anti-Patterns to Avoid

1. **Don't guess CI failures** - Read PR comments (CodeQL, policy bot) and failed run logs first
2. **Don't merge main into feature branches** - Always rebase
3. **Don't force push to main** - Only to feature branches
4. **Don't skip CI** - Wait for checks to pass
5. **Don't commit secrets** - Even for "testing"
6. **Don't skip risk labels** - Every PR needs one
7. **Don't create PRs without ticket references** - Link to tickets
8. **Don't work in the main checkout** - Use worktrees for ticket work.
9. **Don't leave merged worktrees around** - After a PR is merged, remove the worktree, delete the local branch, and run `bin/vibe doctor`.
10. **Don't use `cd path && command`** - Use `git -C path`, `npm --prefix path`, or `gh pr create --repo owner/repo` so commands can run without changing directory and can be parallelized when appropriate.
11. **Don't use multiple worktree systems for the same ticket** - If using `bin/vibe do`, do not also use Claude Code's `isolation: "worktree"` for the same ticket. This creates duplicate branches and duplicate PRs. See [Avoiding Duplicate PRs](#avoiding-duplicate-prs-multiple-worktree-systems).

---

## When Things Go Wrong

- **Rebase conflicts:** `git rebase --abort` to start over, or resolve files and `git rebase --continue`.
- **Accidentally committed a secret:** Remove from code, push the fix, rotate the secret. See `recipes/security/secret-management.md`.
- **Worktree in bad state:** `git worktree remove --force <path>`, then `git branch -D PROJ-123`, then `bin/vibe do PROJ-123` to recreate. See [Cleaning Up Worktrees](#cleaning-up-worktrees--follow-this-order).
- **CORS errors:** Run `bin/vibe cors-check <url> -o <origin>` to diagnose, then apply fixes from `recipes/debugging/cors-errors.md`.
