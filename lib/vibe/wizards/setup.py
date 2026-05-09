"""Initial setup wizard orchestrator."""

import shutil
from pathlib import Path

import click

from lib.vibe.config import DEFAULT_CONFIG, config_exists, load_config, save_config
from lib.vibe.env import setup_direnv
from lib.vibe.state import DEFAULT_STATE, save_state, state_exists
from lib.vibe.ui.components import (
    MultiSelect,
    ProgressIndicator,
    SkillLevel,
    SkillLevelSelector,
    WhatNextFlow,
)
from lib.vibe.ui.context import WizardContext
from lib.vibe.wizards.branch import run_branch_wizard
from lib.vibe.wizards.costs import run_costs_wizard
from lib.vibe.wizards.database import run_database_wizard
from lib.vibe.wizards.env import run_env_wizard
from lib.vibe.wizards.fly import run_fly_wizard
from lib.vibe.wizards.github import (
    run_dependency_graph_prompt,
    run_github_wizard,
    try_auto_configure_github,
)
from lib.vibe.wizards.neon import run_neon_wizard
from lib.vibe.wizards.playwright import run_playwright_wizard
from lib.vibe.wizards.sentry import run_sentry_wizard
from lib.vibe.wizards.supabase import run_supabase_wizard
from lib.vibe.wizards.tracker import run_tracker_wizard
from lib.vibe.wizards.vercel import run_vercel_wizard

# Default PR template when .github/PULL_REQUEST_TEMPLATE.md is missing
_DEFAULT_PR_TEMPLATE = """## Summary

<!-- Brief description of the changes. Link to the ticket. -->

Closes #<!-- ticket number -->

## Changes

<!-- Bullet points of what changed -->

-

## Risk Assessment

<!-- Select one risk level and delete the others -->

- [ ] **Low Risk** - Minimal scope, well-tested, low blast radius
- [ ] **Medium Risk** - Moderate scope, may affect multiple components
- [ ] **High Risk** - Large scope, critical path, or infrastructure changes

## Testing

- [ ] Unit tests added/updated
- [ ] Manual testing instructions included (for non-trivial changes)

## Checklist

- [ ] Code follows project conventions
- [ ] No secrets or credentials committed
- [ ] PR title includes ticket reference
- [ ] Risk label added
"""


def is_fresh_project(config: dict, config_file_existed: bool) -> bool:
    """
    Return True if this looks like a fresh/unconfigured project.

    Fresh = no config file existed, or config has no GitHub owner/repo
    and no tracker configured.
    """
    if not config_file_existed:
        return True
    github = config.get("github") or {}
    owner = github.get("owner") or ""
    repo = github.get("repo") or ""
    tracker_type = (config.get("tracker") or {}).get("type")
    return (not owner.strip() or not repo.strip()) and tracker_type is None


def apply_git_workflow_defaults(config: dict) -> None:
    """Apply sensible git workflow defaults (branching, worktrees) without prompting."""
    config["branching"] = dict(DEFAULT_CONFIG["branching"])
    config["worktrees"] = dict(DEFAULT_CONFIG["worktrees"])


def ensure_pr_template(base_path: Path | None = None) -> bool:
    """
    Ensure .github/PULL_REQUEST_TEMPLATE.md exists; create from default if missing.

    Returns True if the file existed or was created.
    """
    root = base_path or Path(".")
    template_path = root / ".github" / "PULL_REQUEST_TEMPLATE.md"
    if template_path.exists():
        return True
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(_DEFAULT_PR_TEMPLATE, encoding="utf-8")
    return True


def ensure_local_state(base_path: Path | None = None) -> bool:
    """
    Ensure .vibe/local_state.json exists; create from default if missing.

    Returns True if the file existed or was created.
    """
    if state_exists(base_path):
        return True
    save_state(DEFAULT_STATE.copy(), base_path)
    return True


_COMMIT_CONVENTION_CONTENT = """# Commit message convention

Use the format: **TICKET-123: Short description**

- Prefix with the ticket ID (e.g. PROJ-123) when the change relates to a ticket.
- Use present tense: "Add feature" not "Added feature".
- Keep the subject line under ~72 characters.
"""


def ensure_commit_convention(base_path: Path | None = None) -> bool:
    """
    Ensure .github/COMMIT_CONVENTION.md exists; create from default if missing.

    Returns True if the file existed or was created.
    """
    root = base_path or Path(".")
    path = root / ".github" / "COMMIT_CONVENTION.md"
    if path.exists():
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_COMMIT_CONVENTION_CONTENT, encoding="utf-8")
    return True


def ensure_direnv(base_path: Path | None = None) -> None:
    """
    Set up direnv for automatic env variable loading and print status.

    Creates .envrc, updates .gitignore, and runs direnv allow if available.
    """
    root = base_path or Path(".")
    result = setup_direnv(root)

    if result["envrc_created"]:
        click.echo("  • direnv: created .envrc (loads .env.local automatically)")
    else:
        click.echo("  • direnv: .envrc already exists")

    if result["gitignore_updated"]:
        click.echo("  • gitignore: added .envrc and .direnv/")

    if shutil.which("direnv"):
        if result["direnv_allowed"]:
            click.echo("  • direnv: allowed (env vars will load automatically)")
        else:
            click.echo("  • direnv: installed but could not run 'direnv allow'")
            click.echo("    Run 'direnv allow' manually in the project root")
    else:
        click.echo("  • direnv: not installed (optional but recommended)")
        click.echo("    Install: https://direnv.net/docs/installation.html")
        click.echo("    After installing, run 'direnv allow' in the project root")


def _run_multi_assistant_generation() -> None:
    """Run multi-assistant instruction file generation."""
    try:
        from lib.vibe.agents.generator import InstructionGenerator
        from lib.vibe.agents.spec import AssistantFormat, InstructionSpec
    except ImportError:
        click.echo("  Agent instruction generation modules not available.")
        return

    source_path = Path("agent_instructions")
    if not source_path.exists():
        click.echo("  No agent_instructions/ directory found. Skipping.")
        click.echo("  Create agent_instructions/ with CORE.md, COMMANDS.md, WORKFLOW.md")
        return

    # Multi-select for format selection
    format_select = MultiSelect(
        title="Select formats to generate:",
        options=[
            ("CLAUDE.md", "Claude Code instructions", True),
            (".cursor/rules", "Cursor IDE instructions", True),
            (".github/copilot-instructions.md", "GitHub Copilot instructions", False),
        ],
    )
    selected = format_select.show()

    if not selected:
        click.echo("  No formats selected. Skipping generation.")
        return

    format_map = {
        1: AssistantFormat.CLAUDE,
        2: AssistantFormat.CURSOR,
        3: AssistantFormat.COPILOT,
    }
    selected_formats = [format_map[i] for i in selected]

    # Load spec and generate
    try:
        click.echo("  Loading instruction spec...")
        spec = InstructionSpec.from_files(source_path)
        generator = InstructionGenerator(spec)
        results = generator.generate_all(Path("."), selected_formats)

        click.echo("  Generated files:")
        for format_name, file_path in results.items():
            click.echo(f"    - {file_path}")
    except (OSError, ValueError) as e:
        click.echo(f"  Error generating instructions: {e}")


def run_setup(force: bool = False, quick: bool = False) -> bool:
    """
    Run the initial setup wizard.

    On a fresh project (no config or unconfigured), auto-initializes git workflow
    defaults and GitHub from gh CLI + remote when possible, with no prompts.

    Args:
        force: Force re-running setup even if config exists
        quick: Quick mode - sensible defaults, no prompts, skip optional config

    Returns:
        True if setup completed successfully
    """
    config_file_existed = config_exists()
    config = load_config()

    # Quick mode OR fresh project: zero-prompt auto-initialization
    if quick or (is_fresh_project(config, config_file_existed) and not force):
        apply_git_workflow_defaults(config)
        config["tracker"]["type"] = None
        config["tracker"]["config"] = {}
        ensure_pr_template()
        ensure_local_state()
        ensure_commit_convention()
        github_configured = try_auto_configure_github(config)
        save_config(config)
        click.echo("=" * 60)
        click.echo("  Setup Complete (auto-configured)")
        click.echo("=" * 60)
        click.echo()
        click.echo("Detected fresh project. Configured with no prompts:")
        click.echo("  • Git workflow: branch pattern {PROJ}-{num}, worktrees, rebase onto main")
        click.echo("  • PR template: .github/PULL_REQUEST_TEMPLATE.md")
        click.echo("  • Commit convention: .github/COMMIT_CONVENTION.md")
        click.echo("  • Local state: .vibe/local_state.json")
        ensure_direnv()
        if github_configured:
            click.echo("  • GitHub: gh CLI + current repo")
            run_dependency_graph_prompt(config)
        else:
            click.echo("  • GitHub: not configured (run 'bin/vibe setup -w github' when ready)")
        click.echo()
        click.echo("Configuration saved to .vibe/config.json")
        click.echo()
        click.echo("Next steps:")
        click.echo("  1. Run 'bin/doctor' to verify your setup")
        next_num = 2
        if not github_configured:
            click.echo(f"  {next_num}. Run 'bin/vibe setup -w github' to connect GitHub")
            next_num += 1
        click.echo(f"  {next_num}. Optional: run 'bin/vibe setup -w tracker' to add Linear")
        next_num += 1
        click.echo(
            f"  {next_num}. Fill in the Project Overview in CLAUDE.md (for AI agent context)"
        )
        next_num += 1
        click.echo(
            f"  {next_num}. Update README.md with app name, description, tech stack, and setup instructions"
        )
        next_num += 1
        click.echo(f"  {next_num}. Check recipes/ for best practices")
        click.echo()
        click.echo("Infrastructure (configure early for smooth deploys):")
        click.echo("  • Database: bin/vibe setup -w database")
        click.echo("  • Hosting:  bin/vibe setup -w vercel  (or -w fly)")
        click.echo("  • Errors:   Add SENTRY_DSN to .env.local")
        click.echo()
        return True

    # Existing config or reconfiguration: show wizard header and possibly confirm
    click.echo("=" * 60)
    click.echo("  Vibe Code Boilerplate - Setup Wizard")
    click.echo("=" * 60)
    click.echo()

    # Only ask to reconfigure when they already have a real config (not fresh)
    already_configured = config_file_existed and not is_fresh_project(config, config_file_existed)
    if already_configured and not force:
        click.echo("Configuration already exists at .vibe/config.json")
        if not click.confirm("Do you want to reconfigure?", default=False):
            click.echo("Setup cancelled. Use 'vibe setup --force' to reconfigure.")
            return False
        config = load_config()

    # Ask for skill level to adapt wizard verbosity
    skill_selector = SkillLevelSelector()
    skill_level = skill_selector.show()

    # Calculate total steps (varies based on what's already configured)
    github_configured = config.get("github", {}).get("auth_method") and config.get(
        "github", {}
    ).get("owner")
    total_steps = 2 if github_configured else 3  # GitHub + Tracker (+ optional)

    progress = ProgressIndicator(total_steps=total_steps)

    # Essential wizards (required)
    click.echo("\n--- Essential Configuration ---\n")

    # 1. GitHub auth (skip if already configured)
    if github_configured:
        click.echo("GitHub already configured, skipping.")
    else:
        progress.advance("GitHub Authentication")
        if skill_level == SkillLevel.BEGINNER:
            click.echo("Info: GitHub is used for repository access, PR creation, and CI/CD.")
        if not run_github_wizard(config):
            click.echo("GitHub authentication is required. Setup cancelled.")
            return False

    run_dependency_graph_prompt(config)

    # 2. Tracker selection
    progress.advance("Ticket Tracker")
    if skill_level == SkillLevel.BEGINNER:
        click.echo("Info: A ticket tracker helps organize work and link PRs to tasks.")
    if not run_tracker_wizard(config):
        click.echo("Tracker configuration is required. Setup cancelled.")
        return False

    # Save after essentials
    save_config(config)

    # Optional wizards (skip for experts)
    if skill_level != SkillLevel.EXPERT:
        click.echo("\n--- Optional Configuration ---\n")

        if click.confirm("Configure branch naming convention?", default=False):
            run_branch_wizard(config)
            save_config(config)

        if click.confirm("Configure environment/secrets handling?", default=False):
            run_env_wizard(config)
            save_config(config)

        # Multi-assistant instruction generation
        if click.confirm("Generate instruction files for multiple AI assistants?", default=False):
            _run_multi_assistant_generation()
    else:
        click.echo("\n(Skipping optional configuration for expert mode)")

    # Set up direnv for automatic env loading
    click.echo("\n--- Environment Loading ---\n")
    ensure_direnv()

    # Final save and summary
    save_config(config)

    click.echo("\n" + "=" * 60)
    click.echo("  Setup Complete!")
    click.echo("=" * 60)
    click.echo()
    click.echo("Configuration saved to .vibe/config.json")
    click.echo()

    # Prominent reminder about CLAUDE.md
    click.echo("+" + "-" * 58 + "+")
    click.echo("|  IMPORTANT: Update the Project Overview in CLAUDE.md    |")
    click.echo("+" + "-" * 58 + "+")
    click.echo("|                                                          |")
    click.echo("|  AI agents need project context to help effectively.     |")
    click.echo("|  Open CLAUDE.md and fill in:                             |")
    click.echo("|                                                          |")
    click.echo("|  - What this project does                                |")
    click.echo("|  - Tech stack (backend, frontend, database, deployment)  |")
    click.echo("|  - Key features / domains                                |")
    click.echo("|                                                          |")
    click.echo("+" + "-" * 58 + "+")
    click.echo()

    click.echo("Next steps:")
    click.echo("  1. Run 'bin/vibe doctor' to verify your setup")
    click.echo("  2. Update CLAUDE.md Project Overview (see above)")
    click.echo("  3. Update README.md with app name, tech stack, and setup instructions")
    click.echo("  4. If using Linear: add LINEAR_API_KEY to .env.local")
    click.echo("  5. Check out the recipes/ directory for best practices")
    click.echo()
    click.echo("Infrastructure (configure early for smooth deploys):")
    click.echo("  • Database: bin/vibe setup -w database")
    click.echo("  • Hosting:  bin/vibe setup -w vercel  (or -w fly)")
    click.echo("  • Errors:   Add SENTRY_DSN to .env.local")
    click.echo()

    return True


def run_individual_wizard(wizard_name: str, show_what_next: bool = True) -> bool:
    """
    Run a specific wizard by name.

    Args:
        wizard_name: Name of wizard to run (github, tracker, branch, env)
        show_what_next: Whether to show the 'what next?' flow after completion

    Returns:
        True if wizard completed successfully
    """
    config = load_config()

    wizards = {
        "github": run_github_wizard,
        "tracker": run_tracker_wizard,
        "branch": run_branch_wizard,
        "env": run_env_wizard,
        "vercel": run_vercel_wizard,
        "fly": run_fly_wizard,
        "supabase": run_supabase_wizard,
        "neon": run_neon_wizard,
        "database": run_database_wizard,
        "sentry": run_sentry_wizard,
        "playwright": run_playwright_wizard,
        "cost-tracking": run_costs_wizard,
    }

    if wizard_name not in wizards:
        click.echo(f"Unknown wizard: {wizard_name}")
        click.echo(f"Available wizards: {', '.join(wizards.keys())}")
        return False

    result = wizards[wizard_name](config)
    if result:
        save_config(config)

        # Show context-aware recommendations
        context = WizardContext(config)
        recommendation = context.get_recommendation(wizard_name)
        if recommendation:
            rec_wizard, reason = recommendation
            click.echo()
            click.echo(f"Tip: {reason}")

        # Show 'what next?' flow for natural wizard chaining
        if show_what_next:
            what_next = WhatNextFlow(wizard_name, config)
            next_wizard = what_next.show()
            if next_wizard:
                click.echo()
                return run_individual_wizard(next_wizard, show_what_next=True)

    return result
