"""Ticket CLI commands."""

import os
import sys
from pathlib import Path

import click
import requests

# Auto-load .env files at startup (unless disabled)
if os.environ.get("VIBE_NO_DOTENV") != "1":
    from lib.vibe.env import auto_load_env

    auto_load_env(verbose=os.environ.get("VIBE_VERBOSE") == "1")

from lib.vibe.config import load_config, save_config
from lib.vibe.deployment_followup import (
    build_human_followup_body,
    detect_deployment_platforms,
    get_default_human_followup_title,
)
from lib.vibe.trackers.base import Ticket
from lib.vibe.trackers.github_issues import GitHubIssuesTracker
from lib.vibe.trackers.linear import LinearTracker
from lib.vibe.trackers.shortcut import ShortcutTracker
from lib.vibe.ui.components import NumberedMenu, ProgressIndicator, Spinner
from lib.vibe.wizards.tracker import run_tracker_wizard


def get_tracker():
    """Get the configured tracker instance (config file or LINEAR_* env for CI)."""
    config = load_config()
    tracker_type = config.get("tracker", {}).get("type")
    tracker_config = config.get("tracker", {}).get("config", {})

    if tracker_type == "linear":
        return LinearTracker(team_id=tracker_config.get("team_id"))
    if tracker_type == "shortcut":
        return ShortcutTracker()
    if tracker_type == "github":
        return GitHubIssuesTracker(repo=tracker_config.get("repo"))
    # CI: allow Linear via env when no tracker is configured (e.g. HUMAN follow-up workflow)
    if os.environ.get("LINEAR_API_KEY"):
        return LinearTracker(
            team_id=tracker_config.get("team_id") or os.environ.get("LINEAR_TEAM_ID")
        )
    return None


def ensure_tracker_configured():
    """
    Return the configured tracker, or prompt to run the tracker setup wizard.
    Exits with a message if the user declines or setup does not configure a tracker.
    """
    tracker = get_tracker()
    if tracker is not None:
        return tracker

    click.echo(
        "No ticketing system (e.g. Linear) is configured. Set up a tracker before creating or viewing tickets."
    )
    if not click.confirm("Run tracker setup now?", default=True):
        click.echo(
            "Run 'bin/vibe setup' or 'bin/vibe setup --wizard tracker' when ready.", err=True
        )
        sys.exit(1)

    config = load_config()
    if not run_tracker_wizard(config):
        click.echo(
            "Tracker setup was cancelled or failed. Run 'bin/vibe setup' to try again.", err=True
        )
        sys.exit(1)
    save_config(config)

    tracker = get_tracker()
    if tracker is None:
        click.echo(
            "No tracker was selected. Run 'bin/vibe setup' to configure one later.", err=True
        )
        sys.exit(1)
    return tracker


@click.group()
def main() -> None:
    """Ticket management commands."""
    pass


@main.command()
@click.argument("ticket_id")
@click.option("--children", "-c", is_flag=True, help="Include sub-tasks (children)")
def get(ticket_id: str, children: bool) -> None:
    """Get details for a specific ticket."""
    tracker = ensure_tracker_configured()

    try:
        # Use include_children if supported
        with Spinner(f"Fetching ticket {ticket_id}"):
            if hasattr(tracker, "get_ticket") and children:
                ticket = tracker.get_ticket(ticket_id, include_children=True)
            else:
                ticket = tracker.get_ticket(ticket_id)
        if ticket:
            print_ticket(ticket, show_children=children)
        else:
            click.echo(f"Ticket not found: {ticket_id}")
            sys.exit(1)
    except NotImplementedError as e:
        click.echo(str(e), err=True)
        sys.exit(1)


@main.command("list")
@click.option("--status", "-s", help="Filter by status")
@click.option("--label", "-l", multiple=True, help="Filter by label")
@click.option("--limit", "-n", default=50, help="Maximum tickets to show (default: 50)")
@click.option("--all", "fetch_all", is_flag=True, help="Fetch all matching tickets")
@click.option("--project", "-p", help="Filter by project name")
@click.option("--parent", help="Filter by parent ticket (show sub-tasks)")
@click.option(
    "--priority",
    type=click.Choice(["urgent", "high", "medium", "low", "none"], case_sensitive=False),
    help="Filter by priority",
)
@click.option("--assignee", "-a", help="Filter by assignee name (or 'me')")
@click.option("--unassigned", is_flag=True, help="Show only unassigned tickets")
@click.option("--view", "-V", help="Use a named Linear custom view as filter (Linear only)")
@click.option("--unblocked", is_flag=True, help="Show only tickets with no blocking dependencies")
def list_tickets(
    status: str | None,
    label: tuple,
    limit: int,
    fetch_all: bool,
    project: str | None,
    parent: str | None,
    priority: str | None,
    assignee: str | None,
    unassigned: bool,
    view: str | None,
    unblocked: bool,
) -> None:
    """List tickets from the tracker.

    Examples:

        bin/ticket list --status "In Progress"
        bin/ticket list --project "Q1 Roadmap"
        bin/ticket list --parent PROJ-100  # Show sub-tasks
        bin/ticket list --priority urgent
        bin/ticket list --assignee me
        bin/ticket list --unassigned
        bin/ticket list --all  # Fetch all matching tickets
        bin/ticket list --view "Active"  # Use Linear custom view
        bin/ticket list --view "Backlog" --unblocked  # Combine view with unblocked filter
    """
    tracker = ensure_tracker_configured()

    # --view and --unblocked require Linear tracker
    if (view or unblocked) and not isinstance(tracker, LinearTracker):
        click.echo(
            "The --view and --unblocked flags are only supported with the Linear tracker.", err=True
        )
        sys.exit(1)

    effective_limit = 10000 if fetch_all else limit

    try:
        # Build kwargs for trackers that support extended filters
        kwargs: dict = {
            "status": status,
            "labels": list(label) if label else None,
            "limit": effective_limit,
        }
        # Add extended filters if supported
        if hasattr(tracker, "list_tickets"):
            import inspect

            sig = inspect.signature(tracker.list_tickets)
            params = sig.parameters
            if "project" in params and project:
                kwargs["project"] = project
            if "parent" in params and parent:
                kwargs["parent"] = parent
            if "priority" in params and priority:
                kwargs["priority"] = priority
            if "assignee" in params and assignee:
                kwargs["assignee"] = assignee
            if "unassigned" in params and unassigned:
                kwargs["unassigned"] = unassigned
            if "view" in params and view:
                kwargs["view"] = view
            if "unblocked" in params and unblocked:
                kwargs["unblocked"] = unblocked

        spinner_msg = "Fetching tickets"
        if view:
            spinner_msg = f"Fetching tickets (view: {view})"
        with Spinner(spinner_msg):
            tickets = tracker.list_tickets(**kwargs)

        if not tickets:
            click.echo("No tickets found.")
            return

        for ticket in tickets:
            print_ticket_summary(ticket)

        count = len(tickets)
        if count >= effective_limit and not fetch_all:
            click.echo(f"\nShowing {count} tickets. Use --all to fetch all matching tickets.")
        else:
            click.echo(f"\n{count} ticket(s) found.")
    except RuntimeError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    except NotImplementedError as e:
        click.echo(str(e), err=True)
        sys.exit(1)


@main.command("views")
def list_views() -> None:
    """List available Linear custom views.

    Shows all custom views that can be used with 'bin/ticket list --view NAME'.
    Only supported with the Linear tracker.
    """
    tracker = ensure_tracker_configured()

    if not isinstance(tracker, LinearTracker):
        click.echo("The 'views' command is only supported with the Linear tracker.", err=True)
        sys.exit(1)

    try:
        with Spinner("Fetching custom views"):
            views = tracker.list_views()

        if not views:
            click.echo("No custom views found.")
            return

        for v in views:
            owner = v.get("owner", "")
            owner_str = f" (owner: {owner})" if owner else ""
            click.echo(f"  {v['name']}{owner_str}")

        click.echo(f"\n{len(views)} view(s) found.")
        click.echo('Use: bin/ticket list --view "<name>" to apply a view\'s filters.')
    except RuntimeError as e:
        click.echo(str(e), err=True)
        sys.exit(1)


@main.command()
@click.argument("title", required=False)
@click.option("--description", "-d", default="", help="Ticket description (required)")
@click.option("--label", "-l", multiple=True, help="Labels to add")
@click.option("--blocked-by", multiple=True, help="Ticket IDs that block this ticket")
@click.option("--relates-to", multiple=True, help="Related ticket IDs (non-hierarchical)")
@click.option("--interactive", "-i", is_flag=True, help="Interactive mode with guided prompts")
@click.option("--project", "-p", help="Add to project (by name)")
@click.option("--parent", help="Parent ticket ID (creates as sub-task)")
@click.option(
    "--priority",
    type=click.Choice(["urgent", "high", "medium", "low", "none"], case_sensitive=False),
    help="Set priority level",
)
@click.option("--assignee", "-a", help="Assign to user (name or 'me')")
@click.option(
    "--allow-empty-description", is_flag=True, hidden=True, help="Skip description requirement"
)
@click.option("--no-labels", is_flag=True, help="Explicitly skip label requirement")
@click.option("--dry-run", is_flag=True, help="Preview ticket without creating")
def create(
    title: str | None,
    description: str,
    label: tuple,
    blocked_by: tuple,
    relates_to: tuple,
    interactive: bool,
    project: str | None,
    parent: str | None,
    priority: str | None,
    assignee: str | None,
    allow_empty_description: bool = False,
    no_labels: bool = False,
    dry_run: bool = False,
) -> None:
    """Create a new ticket.

    A description is required. Use --description/-d to provide context about
    the issue, root cause, affected code, and acceptance criteria.

    Labels are required by default. Use --label/-l to specify them, or
    --no-labels to explicitly skip. In interactive mode (TTY), you'll be
    prompted to select labels if none are provided.

    Use --interactive for guided ticket creation with prompts for
    type, risk, and area labels.

    Examples:

        bin/ticket create "New feature" -d "Add OAuth2 login" -l Feature -l Backend --blocked-by PROJ-123
        bin/ticket create "Sub-task" -d "Implement refresh tokens" -l Feature -l Backend --parent PROJ-100
        bin/ticket create "Urgent fix" -d "Login 500 on special chars" -l Bug -l Backend --priority urgent --assignee me
        bin/ticket create "Q1 work" -d "Sprint planning items" -l Chore -l Backend --project "Q1 Roadmap"
        bin/ticket create "Related work" -d "Add caching layer" -l Feature -l Backend --relates-to PROJ-50
        bin/ticket create "Quick note" -d "Description" --no-labels
    """
    # Interactive mode
    labels: list[str] | None = None
    if interactive:
        title, description, labels = _interactive_create()
    else:
        if not title:
            click.echo("Error: Title is required. Use --interactive for guided mode.", err=True)
            sys.exit(1)
        if not description.strip() and not allow_empty_description:
            click.echo(
                "Error: --description is required. Tickets without descriptions are useless.",
                err=True,
            )
            click.echo(
                'Usage: bin/ticket create "Title" --description "Detailed description"', err=True
            )
            sys.exit(1)
        labels = list(label) if label else None

        # Require labels unless --no-labels is set
        if not labels and not no_labels:
            config = load_config()
            label_config = config.get("labels", {})

            if sys.stdin.isatty():
                # Interactive: prompt for labels
                labels = _prompt_for_labels(label_config)
            else:
                # Non-interactive: fail with helpful error
                _fail_missing_labels(label_config)

    if dry_run:
        click.echo("\nDRY RUN — Would create ticket:")
        click.echo(f"  Title:       {title}")
        if description:
            click.echo(
                f"  Description: {description[:80]}..."
                if len(description) > 80
                else f"  Description: {description}"
            )
        if labels:
            click.echo(f"  Labels:      {', '.join(labels)}")
        if priority:
            click.echo(f"  Priority:    {priority}")
        if parent:
            click.echo(f"  Parent:      {parent}")
        if project:
            click.echo(f"  Project:     {project}")
        if assignee:
            click.echo(f"  Assignee:    {assignee}")
        if relates_to:
            click.echo(f"  Relates to:  {', '.join(relates_to)}")
        click.echo("\nNo ticket was created. Remove --dry-run to create.")
        return

    tracker = ensure_tracker_configured()

    try:
        # Build kwargs for extended create options
        kwargs: dict = {
            "title": title,
            "description": description,
            "labels": labels,
        }
        # Add extended options if supported
        import inspect

        sig = inspect.signature(tracker.create_ticket)
        params = sig.parameters
        if "project" in params and project:
            kwargs["project"] = project
        if "parent" in params and parent:
            kwargs["parent"] = parent
        if "priority" in params and priority:
            kwargs["priority"] = priority
        if "assignee" in params and assignee:
            kwargs["assignee"] = assignee

        with Spinner("Creating ticket"):
            ticket = tracker.create_ticket(**kwargs)
        click.echo(f"Created ticket: {ticket.id}")
        if parent and ticket.parent_id:
            click.echo(f"  (sub-task of {ticket.parent_id})")
        if project and ticket.project:
            click.echo(f"  (in project: {ticket.project})")
        click.echo(f"URL: {ticket.url}")

        # Set up blocking relationships if specified
        if blocked_by and hasattr(tracker, "create_relation"):
            click.echo()
            for blocker_id in blocked_by:
                try:
                    tracker.create_relation(blocker_id, ticket.id, "blocks")
                    click.echo(f"  ✓ {blocker_id} blocks {ticket.id}")
                except RuntimeError as e:
                    click.echo(f"  ✗ Failed to create relation: {e}", err=True)

        # Set up non-hierarchical relations if specified
        if relates_to:
            click.echo()
            for related_id in relates_to:
                try:
                    tracker.add_relation(ticket.id, related_id, "related")
                    click.echo(f"  \u2713 {ticket.id} relates to {related_id}")
                except (RuntimeError, NotImplementedError) as e:
                    click.echo(f"  \u2717 Failed to create relation: {e}", err=True)

    except NotImplementedError as e:
        click.echo(str(e), err=True)
        sys.exit(1)


def _fail_missing_labels(label_config: dict) -> None:
    """Print an error with available label categories and exit.

    Called in non-interactive (non-TTY) mode when no labels are provided.
    """
    type_labels = label_config.get("type", ["Bug", "Feature", "Chore", "Refactor"])
    risk_labels = label_config.get("risk", ["Low Risk", "Medium Risk", "High Risk"])
    area_labels = label_config.get("area", ["Frontend", "Backend", "Infra", "Docs"])

    click.echo("Error: Labels are required when creating tickets.", err=True)
    click.echo("", err=True)
    click.echo("Available label categories:", err=True)
    click.echo(f"  Type (pick one):  {', '.join(type_labels)}", err=True)
    click.echo(f"  Risk (pick one):  {', '.join(risk_labels)}", err=True)
    click.echo(f"  Area (pick one+): {', '.join(area_labels)}", err=True)
    click.echo("", err=True)
    click.echo("Example:", err=True)
    click.echo(
        '  bin/ticket create "Fix login bug" -d "Description" -l Bug -l "High Risk" -l Backend',
        err=True,
    )
    click.echo("", err=True)
    click.echo("To skip labels, use --no-labels.", err=True)
    sys.exit(1)


def _prompt_for_labels(label_config: dict) -> list[str]:
    """Interactively prompt for label selection when in TTY mode.

    Args:
        label_config: The labels section from .vibe/config.json

    Returns:
        List of selected label strings
    """
    labels: list[str] = []

    click.echo()
    click.echo("No labels provided. Select labels for this ticket:")
    click.echo()

    # Type label
    type_labels = label_config.get("type", ["Bug", "Feature", "Chore", "Refactor"])
    type_menu = NumberedMenu(
        title="Select ticket type:",
        options=[(t, "") for t in type_labels],
        default=2,  # Default to Feature
    )
    type_choice = type_menu.show()
    labels.append(type_labels[type_choice - 1])

    # Risk label
    risk_labels = label_config.get("risk", ["Low Risk", "Medium Risk", "High Risk"])
    risk_menu = NumberedMenu(
        title="Select risk level:",
        options=[(r, "") for r in risk_labels],
        default=1,
    )
    risk_choice = risk_menu.show()
    labels.append(risk_labels[risk_choice - 1])

    # Area label
    area_labels = label_config.get("area", ["Frontend", "Backend", "Infra", "Docs"])
    area_menu = NumberedMenu(
        title="Select primary area:",
        options=[(a, "") for a in area_labels],
        default=2,  # Default to Backend
    )
    area_choice = area_menu.show()
    labels.append(area_labels[area_choice - 1])

    click.echo()
    click.echo(f"Selected labels: {', '.join(labels)}")

    return labels


def _interactive_create() -> tuple[str, str, list[str]]:
    """Interactive ticket creation with guided prompts.

    Returns:
        Tuple of (title, description, labels)
    """
    config = load_config()
    label_config = config.get("labels", {})

    click.echo("\n" + "=" * 50)
    click.echo("  Interactive Ticket Creation")
    click.echo("=" * 50)
    click.echo()

    progress = ProgressIndicator(total_steps=5)

    # Step 1: Title
    progress.advance("Ticket title")
    title = click.prompt("Enter ticket title")

    # Step 2: Type label
    progress.advance("Type selection")
    type_labels = label_config.get("type", ["Bug", "Feature", "Chore", "Refactor"])
    type_menu = NumberedMenu(
        title="Select ticket type:",
        options=[(t, "") for t in type_labels],
        default=2,  # Default to Feature
    )
    type_choice = type_menu.show()
    selected_type = type_labels[type_choice - 1]

    # Step 3: Risk label
    progress.advance("Risk assessment")
    risk_labels = label_config.get("risk", ["Low Risk", "Medium Risk", "High Risk"])
    risk_menu = NumberedMenu(
        title="Select risk level:",
        options=[
            ("Low Risk", "Docs, tests, typos, minor UI tweaks"),
            ("Medium Risk", "New features, bug fixes, refactoring"),
            ("High Risk", "Auth, payments, database, infrastructure"),
        ],
        default=1,
    )
    risk_choice = risk_menu.show()
    selected_risk = risk_labels[risk_choice - 1]

    # Step 4: Area label(s)
    progress.advance("Area selection")
    area_labels = label_config.get("area", ["Frontend", "Backend", "Infra", "Docs"])
    area_menu = NumberedMenu(
        title="Select primary area:",
        options=[(a, "") for a in area_labels],
        default=2,  # Default to Backend
    )
    area_choice = area_menu.show()
    selected_area = area_labels[area_choice - 1]

    # Step 5: Description
    progress.advance("Description")
    click.echo("\nEnter description (press Enter twice to finish, or leave blank to skip):")
    description_lines = []
    empty_count = 0
    while True:
        line = click.prompt("", default="", show_default=False)
        if line == "":
            empty_count += 1
            if empty_count >= 1:  # Single empty line ends input
                break
        else:
            empty_count = 0
            description_lines.append(line)
    description = "\n".join(description_lines)

    labels = [selected_type, selected_risk, selected_area]

    # Summary
    click.echo("\n" + "-" * 50)
    click.echo("Summary:")
    click.echo(f"  Title: {title}")
    click.echo(f"  Type: {selected_type}")
    click.echo(f"  Risk: {selected_risk}")
    click.echo(f"  Area: {selected_area}")
    if description:
        click.echo(
            f"  Description: {description[:50]}..."
            if len(description) > 50
            else f"  Description: {description}"
        )
    click.echo("-" * 50)

    if not click.confirm("\nCreate this ticket?", default=True):
        click.echo("Cancelled.")
        sys.exit(0)

    return title, description, labels


HUMAN_FOLLOWUP_LABELS = ["Chore", "Infra", "HUMAN"]


@main.command("create-human-followup")
@click.option(
    "--files",
    "-f",
    multiple=True,
    help="Changed file paths (e.g. from git diff). If not set, scan repo for deployment configs.",
)
@click.option("--parent", "-p", "parent_ticket_id", help="Parent ticket ID (e.g. PROJ-123)")
@click.option("--print-only", is_flag=True, help="Print ticket body only; do not create")
@click.option("--env-path", default=".env.example", help="Path to .env.example for instructions")
def create_human_followup(
    files: tuple,
    parent_ticket_id: str | None,
    print_only: bool,
    env_path: str,
) -> None:
    """Create a HUMAN-labeled follow-up ticket for deployment infrastructure setup.

    Use after completing a deployment infra ticket (fly.toml, vercel.json, .env.example).
    Detects platforms from changed files or repo scan and builds step-by-step instructions.
    """
    config = load_config()
    repo_owner = config.get("github", {}).get("owner", "")
    repo_name = config.get("github", {}).get("repo", "")
    if not repo_owner and not repo_name and os.environ.get("GITHUB_REPOSITORY"):
        parts = os.environ["GITHUB_REPOSITORY"].split("/", 1)
        repo_owner = parts[0] if len(parts) > 0 else ""
        repo_name = parts[1] if len(parts) > 1 else ""
    changed_files = list(files) if files else None
    repo_root = Path.cwd()

    platforms = detect_deployment_platforms(
        changed_files=changed_files,
        repo_root=repo_root,
    )
    if not platforms:
        click.echo(
            "No deployment configs detected. Add --files with paths like fly.toml, vercel.json, .env.example, "
            "or run from a repo that contains them.",
            err=True,
        )
        sys.exit(1)

    body = build_human_followup_body(
        platforms=platforms,
        repo_owner=repo_owner,
        repo_name=repo_name,
        parent_ticket_id=parent_ticket_id,
        env_example_path=env_path,
    )
    title = get_default_human_followup_title()

    if print_only:
        click.echo(f"Title: {title}")
        click.echo(f"Labels: {', '.join(HUMAN_FOLLOWUP_LABELS)}")
        click.echo("\nDescription:\n")
        click.echo(body)
        return

    tracker = ensure_tracker_configured()

    # Deduplication: check if an open ticket with the same title already exists
    terminal_states = {"Done", "Canceled", "Deployed", "Closed", "Cancelled"}
    try:
        existing_tickets = tracker.list_tickets(labels=["HUMAN"], limit=100)
        for existing in existing_tickets:
            if existing.title == title and getattr(existing, "status", "") not in terminal_states:
                click.echo(f"HUMAN follow-up ticket already exists: {existing.id}")
                click.echo(f"URL: {existing.url}")
                click.echo("Skipping duplicate creation.")
                return
    except (requests.RequestException, RuntimeError):
        click.echo(
            "Warning: could not check for existing tickets, proceeding with creation.",
            err=True,
        )

    try:
        ticket = tracker.create_ticket(
            title=title,
            description=body,
            labels=HUMAN_FOLLOWUP_LABELS,
        )
        click.echo(f"Created HUMAN follow-up ticket: {ticket.id}")
        click.echo(f"URL: {ticket.url}")
    except NotImplementedError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    except RuntimeError as e:
        click.echo(str(e), err=True)
        sys.exit(1)


@main.command()
@click.argument("ticket_id")
@click.option("--status", "-s", help="Set ticket status (e.g. Done, In Progress)")
@click.option("--title", "-t", help="Set ticket title")
@click.option("--description", "-d", help="Set ticket description")
@click.option(
    "--label",
    "-l",
    multiple=True,
    help="Add labels (merged with existing labels)",
)
@click.option("--blocked-by", multiple=True, help="Add tickets that block this ticket")
@click.option("--blocks", multiple=True, help="Add tickets that this ticket blocks")
@click.option("--project", "-p", help="Add to project (by name)")
@click.option("--remove-project", is_flag=True, help="Remove from current project")
@click.option("--parent", help="Set parent ticket (make sub-task)")
@click.option("--no-parent", is_flag=True, help="Remove parent (make standalone)")
@click.option(
    "--priority",
    type=click.Choice(["urgent", "high", "medium", "low", "none"], case_sensitive=False),
    help="Set priority level",
)
@click.option("--assignee", "-a", help="Assign to user (name or 'me')")
@click.option("--unassign", is_flag=True, help="Remove assignee")
def update(
    ticket_id: str,
    status: str | None,
    title: str | None,
    description: str | None,
    label: tuple,
    blocked_by: tuple,
    blocks: tuple,
    project: str | None,
    remove_project: bool,
    parent: str | None,
    no_parent: bool,
    priority: str | None,
    assignee: str | None,
    unassign: bool,
) -> None:
    """Update a ticket (status, title, description, labels, relations, project, parent).

    Examples:

        bin/ticket update PROJ-456 --blocked-by PROJ-123
        bin/ticket update PROJ-456 --blocks PROJ-789
        bin/ticket update PROJ-456 --project "Q1 Roadmap"
        bin/ticket update PROJ-456 --parent PROJ-100  # Make sub-task
        bin/ticket update PROJ-456 --no-parent  # Make standalone
        bin/ticket update PROJ-456 --priority urgent --assignee me
    """
    tracker = ensure_tracker_configured()

    has_field_update = any(
        [
            status,
            title,
            description,
            label,
            project,
            remove_project,
            parent,
            no_parent,
            priority,
            assignee,
            unassign,
        ]
    )
    has_relation_update = any([blocked_by, blocks])

    if not has_field_update and not has_relation_update:
        click.echo(
            "Specify at least one of: --status, --title, --description, --label, "
            "--blocked-by, --blocks, --project, --parent, --priority, --assignee",
            err=True,
        )
        sys.exit(1)

    # Update ticket fields if any specified
    if has_field_update:
        try:
            # Build kwargs for extended update options
            import inspect

            kwargs: dict = {
                "title": title,
                "description": description,
                "status": status,
                "labels": list(label) if label else None,
            }
            sig = inspect.signature(tracker.update_ticket)
            params = sig.parameters
            if "project" in params and project:
                kwargs["project"] = project
            if "remove_project" in params and remove_project:
                kwargs["remove_project"] = remove_project
            if "parent" in params and parent:
                kwargs["parent"] = parent
            if "remove_parent" in params and no_parent:
                kwargs["remove_parent"] = no_parent
            if "priority" in params and priority:
                kwargs["priority"] = priority
            if "assignee" in params and assignee:
                kwargs["assignee"] = assignee
            if "unassign" in params and unassign:
                kwargs["unassign"] = unassign

            ticket = tracker.update_ticket(ticket_id, **kwargs)
            click.echo(f"Updated: {ticket.id}")
            click.echo(f"Status: {ticket.status}")
            if ticket.project:
                click.echo(f"Project: {ticket.project}")
            if ticket.parent_id:
                click.echo(f"Parent: {ticket.parent_id}")
            if ticket.assignee:
                click.echo(f"Assignee: {ticket.assignee}")
            if ticket.priority is not None:
                from lib.vibe.trackers.linear import PRIORITY_NAMES

                priority_name = PRIORITY_NAMES.get(ticket.priority, "unknown")
                click.echo(f"Priority: {priority_name}")
            click.echo(f"URL: {ticket.url}")
        except NotImplementedError as e:
            click.echo(str(e), err=True)
            sys.exit(1)
        except RuntimeError as e:
            click.echo(str(e), err=True)
            sys.exit(1)

    # Set up blocking relationships if specified
    if has_relation_update and hasattr(tracker, "create_relation"):
        click.echo()
        # blocked_by: other tickets block this one
        for blocker_id in blocked_by:
            try:
                tracker.create_relation(blocker_id, ticket_id, "blocks")
                click.echo(f"  ✓ {blocker_id} blocks {ticket_id}")
            except RuntimeError as e:
                click.echo(f"  ✗ Failed to create relation: {e}", err=True)

        # blocks: this ticket blocks other tickets
        for blocked_id in blocks:
            try:
                tracker.create_relation(ticket_id, blocked_id, "blocks")
                click.echo(f"  ✓ {ticket_id} blocks {blocked_id}")
            except RuntimeError as e:
                click.echo(f"  ✗ Failed to create relation: {e}", err=True)


@main.command()
@click.argument("ticket_id")
@click.option("--cancel", is_flag=True, help="Mark as canceled instead of done")
def close(ticket_id: str, cancel: bool) -> None:
    """Close a ticket (set status to Done or Canceled)."""
    tracker = ensure_tracker_configured()

    status = "Canceled" if cancel else "Done"
    try:
        ticket = tracker.update_ticket(ticket_id, status=status)
        click.echo(f"Closed: {ticket.id} ({ticket.status})")
        click.echo(f"URL: {ticket.url}")
    except NotImplementedError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    except RuntimeError as e:
        click.echo(str(e), err=True)
        sys.exit(1)


@main.command()
@click.argument("ticket_id")
@click.option("--blocks", multiple=True, help="Ticket IDs that this ticket blocks")
@click.option("--blocked-by", multiple=True, help="Ticket IDs that block this ticket")
def relate(ticket_id: str, blocks: tuple, blocked_by: tuple) -> None:
    """Set up blocking relationships for a ticket.

    Use this command to quickly set up multiple blocking relationships:

        bin/ticket relate PROJ-123 --blocks PROJ-456 PROJ-457 PROJ-458
        bin/ticket relate PROJ-123 --blocked-by PROJ-100
    """
    tracker = ensure_tracker_configured()

    if not blocks and not blocked_by:
        click.echo("Specify at least one of: --blocks, --blocked-by", err=True)
        sys.exit(1)

    if not hasattr(tracker, "create_relation"):
        click.echo("This tracker does not support blocking relationships", err=True)
        sys.exit(1)

    success_count = 0
    fail_count = 0

    # This ticket blocks others
    for blocked_id in blocks:
        try:
            tracker.create_relation(ticket_id, blocked_id, "blocks")
            click.echo(f"  ✓ {ticket_id} blocks {blocked_id}")
            success_count += 1
        except RuntimeError as e:
            click.echo(f"  ✗ {ticket_id} -> {blocked_id}: {e}", err=True)
            fail_count += 1

    # Other tickets block this one
    for blocker_id in blocked_by:
        try:
            tracker.create_relation(blocker_id, ticket_id, "blocks")
            click.echo(f"  ✓ {blocker_id} blocks {ticket_id}")
            success_count += 1
        except RuntimeError as e:
            click.echo(f"  ✗ {blocker_id} -> {ticket_id}: {e}", err=True)
            fail_count += 1

    click.echo()
    click.echo(
        f"Created {success_count} relation(s)" + (f", {fail_count} failed" if fail_count else "")
    )


@main.command()
@click.argument("ticket_id")
@click.argument("message")
def comment(ticket_id: str, message: str) -> None:
    """Add a comment to a ticket."""
    tracker = ensure_tracker_configured()

    try:
        tracker.comment_ticket(ticket_id, message)
        click.echo(f"Comment added to {ticket_id}")
    except NotImplementedError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    except RuntimeError as e:
        click.echo(str(e), err=True)
        sys.exit(1)


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def labels(as_json: bool) -> None:
    """List all labels with their IDs.

    Useful for API calls that require label IDs instead of names.
    """
    tracker = ensure_tracker_configured()

    if not hasattr(tracker, "list_labels"):
        click.echo("Label listing not supported for this tracker", err=True)
        sys.exit(1)

    try:
        label_list = tracker.list_labels()
        if not label_list:
            click.echo("No labels found.")
            return

        if as_json:
            import json

            click.echo(json.dumps(label_list, indent=2))
        else:
            click.echo("\nLabels:")
            click.echo("-" * 60)
            for label in sorted(label_list, key=lambda x: x.get("name", "")):
                name = label.get("name", "")
                label_id = label.get("id", "")
                color = label.get("color", "")
                click.echo(f"  {name:<30} {label_id}")
                if color:
                    click.echo(f"    Color: {color}")
            click.echo()
            click.echo("Tip: Use label IDs in API calls for reliability.")
    except NotImplementedError as e:
        click.echo(str(e), err=True)
        sys.exit(1)


@main.command("projects")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option(
    "--state",
    type=click.Choice(["planned", "started", "completed", "canceled"], case_sensitive=False),
    help="Filter by project state",
)
def list_projects(as_json: bool, state: str | None) -> None:
    """List all projects.

    Examples:

        bin/ticket projects
        bin/ticket projects --state started
        bin/ticket projects --json
    """
    tracker = ensure_tracker_configured()

    if not hasattr(tracker, "list_projects"):
        click.echo("Project listing not supported for this tracker", err=True)
        sys.exit(1)

    try:
        projects = tracker.list_projects(state=state)
        if not projects:
            click.echo("No projects found.")
            return

        if as_json:
            import json

            click.echo(
                json.dumps(
                    [
                        {"id": p.id, "name": p.name, "state": p.state, "url": p.url}
                        for p in projects
                    ],
                    indent=2,
                )
            )
        else:
            click.echo("\nProjects:")
            click.echo("-" * 60)
            for project in projects:
                state_str = f" ({project.state})" if project.state else ""
                click.echo(f"  {project.name}{state_str}")
                if project.description:
                    click.echo(f"    {project.description[:50]}...")
            click.echo()
    except (requests.RequestException, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command("project")
@click.argument("action", type=click.Choice(["create", "get"]))
@click.argument("name")
@click.option("--description", "-d", default="", help="Project description")
@click.option(
    "--state",
    type=click.Choice(["planned", "started", "completed", "canceled"], case_sensitive=False),
    default="planned",
    help="Initial project state",
)
def project_command(action: str, name: str, description: str, state: str) -> None:
    """Manage projects.

    Examples:

        bin/ticket project create "Q1 Roadmap" --description "Q1 goals"
        bin/ticket project get "Q1 Roadmap"
    """
    tracker = ensure_tracker_configured()

    if action == "create":
        if not hasattr(tracker, "create_project"):
            click.echo("Project creation not supported for this tracker", err=True)
            sys.exit(1)
        try:
            project = tracker.create_project(name=name, description=description, state=state)
            click.echo(f"Created project: {project.name}")
            click.echo(f"ID: {project.id}")
            click.echo(f"URL: {project.url}")
        except (requests.RequestException, RuntimeError) as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

    elif action == "get":
        if not hasattr(tracker, "get_project"):
            click.echo("Project retrieval not supported for this tracker", err=True)
            sys.exit(1)
        try:
            project = tracker.get_project(name)
            if project:
                click.echo(f"\n{project.name}")
                click.echo("-" * 40)
                click.echo(f"ID: {project.id}")
                click.echo(f"State: {project.state}")
                if project.description:
                    click.echo(f"Description: {project.description}")
                click.echo(f"URL: {project.url}")
            else:
                click.echo(f"Project not found: {name}")
                sys.exit(1)
        except (requests.RequestException, RuntimeError) as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)


@main.command("users")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_users(as_json: bool) -> None:
    """List all users in the organization.

    Useful for finding assignee names.
    """
    tracker = ensure_tracker_configured()

    if not hasattr(tracker, "list_users"):
        click.echo("User listing not supported for this tracker", err=True)
        sys.exit(1)

    try:
        users = tracker.list_users()
        if not users:
            click.echo("No users found.")
            return

        if as_json:
            import json

            click.echo(json.dumps(users, indent=2))
        else:
            click.echo("\nUsers:")
            click.echo("-" * 60)
            for user in users:
                name = user.get("name", "")
                email = user.get("email", "")
                active = "active" if user.get("active", True) else "inactive"
                click.echo(f"  {name} <{email}> ({active})")
            click.echo()
    except (requests.RequestException, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.group()
def batch() -> None:
    """Batch ticket operations."""
    pass


@batch.command("create")
@click.option(
    "--from",
    "from_file",
    required=True,
    type=click.Path(exists=True),
    help="YAML file with ticket definitions",
)
@click.option("--dry-run", is_flag=True, help="Preview without creating")
def batch_create(from_file: str, dry_run: bool) -> None:
    """Create multiple tickets from a YAML file.

    Example YAML format:

    \b
        tickets:
          - title: "Set up auth"
            description: "Add JWT auth middleware"
            labels: [Feature, Backend, Medium Risk]
            priority: high
          - title: "Add login page"
            description: "Create login UI"
            labels: [Feature, Frontend, Medium Risk]
    """
    try:
        import yaml
    except ImportError:
        click.echo(
            "PyYAML is required for batch operations. Install with: pip install pyyaml", err=True
        )
        sys.exit(1)

    with open(from_file) as f:
        data = yaml.safe_load(f)

    tickets_data = data.get("tickets", [])
    if not tickets_data:
        click.echo("No tickets found in YAML file.")
        return

    if dry_run:
        click.echo(f"DRY RUN — Would create {len(tickets_data)} tickets:\n")
        for i, t in enumerate(tickets_data, 1):
            labels_str = ", ".join(t.get("labels", []))
            click.echo(f'  {i}. "{t["title"]}" ({labels_str})')
            if t.get("description"):
                desc = t["description"][:60]
                click.echo(f"     {desc}...")
        click.echo("\nNo tickets were created. Remove --dry-run to create.")
        return

    tracker = ensure_tracker_configured()
    created = []

    for i, t in enumerate(tickets_data, 1):
        try:
            import inspect

            kwargs: dict = {
                "title": t["title"],
                "description": t.get("description", ""),
                "labels": t.get("labels"),
            }
            sig = inspect.signature(tracker.create_ticket)
            params = sig.parameters
            if "priority" in params and t.get("priority"):
                kwargs["priority"] = t["priority"]
            if "parent" in params and t.get("parent"):
                kwargs["parent"] = t["parent"]
            if "assignee" in params and t.get("assignee"):
                kwargs["assignee"] = t["assignee"]
            if "project" in params and t.get("project"):
                kwargs["project"] = t["project"]

            ticket = tracker.create_ticket(**kwargs)
            created.append(ticket)
            click.echo(f"  Created {ticket.id}: {t['title']}")
        except Exception as e:
            click.echo(f'  Failed to create "{t["title"]}": {e}', err=True)

    click.echo(f"\nCreated {len(created)}/{len(tickets_data)} tickets.")


@batch.command("assign-project")
@click.option(
    "--from",
    "from_file",
    required=True,
    type=click.Path(exists=True),
    help="YAML file with project assignments",
)
@click.option("--dry-run", is_flag=True, help="Preview without updating")
def batch_assign_project(from_file: str, dry_run: bool) -> None:
    """Assign tickets to projects in bulk from a YAML file.

    Example YAML format:

    \b
        projects:
          - name: "Data Pipeline V1"
            tickets: [DEAL-4, DEAL-61, DEAL-62]
          - name: "Backend API"
            tickets: [DEAL-83, DEAL-84, DEAL-85]
    """
    try:
        import yaml
    except ImportError:
        click.echo(
            "PyYAML is required for batch operations. Install with: pip install pyyaml", err=True
        )
        sys.exit(1)

    with open(from_file) as f:
        data = yaml.safe_load(f)

    projects_data = data.get("projects", [])
    if not projects_data:
        click.echo("No projects found in YAML file.")
        return

    # Validate structure
    total_assignments = 0
    for proj in projects_data:
        if "name" not in proj:
            click.echo("Error: each project entry must have a 'name' field.", err=True)
            sys.exit(1)
        tickets = proj.get("tickets", [])
        if not tickets:
            click.echo(f"Warning: project \"{proj['name']}\" has no tickets listed.", err=True)
        total_assignments += len(tickets)

    if dry_run:
        click.echo(f"DRY RUN — Would assign {total_assignments} tickets across {len(projects_data)} projects:\n")
        for proj in projects_data:
            tickets = proj.get("tickets", [])
            ticket_ids = ", ".join(str(t) for t in tickets)
            click.echo(f"  {proj['name']}:")
            click.echo(f"    {ticket_ids}")
        click.echo("\nNo tickets were updated. Remove --dry-run to apply.")
        return

    tracker = ensure_tracker_configured()

    if not hasattr(tracker, "create_project"):
        click.echo("Batch project assignment is only supported for trackers with project support (e.g. Linear).", err=True)
        sys.exit(1)

    succeeded = 0
    failed = 0

    for proj in projects_data:
        project_name = proj["name"]
        tickets = proj.get("tickets", [])
        click.echo(f"\nAssigning to project: {project_name}")
        for ticket_id in tickets:
            ticket_id_str = str(ticket_id)
            try:
                tracker.update_ticket(ticket_id_str, project=project_name)
                click.echo(f"  ✓ {ticket_id_str}")
                succeeded += 1
            except Exception as e:
                click.echo(f"  ✗ {ticket_id_str}: {e}", err=True)
                failed += 1

    click.echo(f"\nAssigned {succeeded}/{total_assignments} tickets.")
    if failed:
        click.echo(f"{failed} failed.", err=True)


def print_ticket(ticket: Ticket, show_children: bool = False) -> None:
    """Print full ticket details."""
    click.echo(f"\n{ticket.id}: {ticket.title}")
    click.echo("-" * 60)
    click.echo(f"Status: {ticket.status}")
    click.echo(f"Labels: {', '.join(ticket.labels) if ticket.labels else 'none'}")

    # Extended fields
    if ticket.priority is not None:
        from lib.vibe.trackers.linear import PRIORITY_NAMES

        priority_name = PRIORITY_NAMES.get(ticket.priority, "unknown")
        click.echo(f"Priority: {priority_name}")
    if ticket.assignee:
        click.echo(f"Assignee: {ticket.assignee}")
    if ticket.project:
        project_str = ticket.project
        if ticket.project_state:
            project_str += f" ({ticket.project_state})"
        click.echo(f"Project: {project_str}")
    if ticket.parent_id:
        parent_str = ticket.parent_id
        if ticket.parent_title:
            parent_str += f" ({ticket.parent_title})"
        click.echo(f"Parent: {parent_str}")

    click.echo(f"URL: {ticket.url}")

    if ticket.description:
        click.echo(f"\nDescription:\n{ticket.description}")

    # Show children (sub-tasks) if requested and present
    if show_children and ticket.children:
        click.echo("\nSub-tasks:")
        for child in ticket.children:
            click.echo(f"  - {child.id}: {child.title} ({child.status})")

    click.echo()


def print_ticket_summary(ticket: Ticket) -> None:
    """Print ticket summary line."""
    labels = f" [{', '.join(ticket.labels)}]" if ticket.labels else ""

    # Build extra info
    extras = []
    if ticket.priority is not None and ticket.priority > 0:
        from lib.vibe.trackers.linear import PRIORITY_NAMES

        priority_name = PRIORITY_NAMES.get(ticket.priority, "")
        if priority_name:
            extras.append(priority_name.upper())
    if ticket.assignee:
        extras.append(f"@{ticket.assignee.split()[0]}")  # First name only
    if ticket.parent_id:
        extras.append(f"↳{ticket.parent_id}")

    extra_str = f" {' '.join(extras)}" if extras else ""
    click.echo(f"  {ticket.id}: {ticket.title} ({ticket.status}){labels}{extra_str}")


if __name__ == "__main__":
    main()
