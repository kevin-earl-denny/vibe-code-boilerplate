"""Ticket tracker selection wizard."""

import os
from typing import Any

import click

from lib.vibe.tools import require_interactive
from lib.vibe.trackers.base import TrackerBase
from lib.vibe.ui.components import NumberedMenu


def run_tracker_wizard(config: dict[str, Any]) -> bool:
    """
    Configure ticket tracker integration.

    Args:
        config: Configuration dict to update

    Returns:
        True if configuration was successful
    """
    # Check prerequisites
    ok, error = require_interactive("Tracker")
    if not ok:
        click.echo(f"\n{error}")
        return False

    menu = NumberedMenu(
        title="Select your ticket tracking system:",
        options=[
            ("Linear", "Full integration with status syncing"),
            ("GitHub Issues", "Use GitHub Issues (no API key needed)"),
            ("Shortcut", "Coming soon (stub)"),
            ("None", "Skip ticket tracking"),
        ],
        default=1,
    )

    choice = menu.show()

    if choice == 1:
        return _setup_linear(config)
    elif choice == 2:
        return _setup_github_issues(config)
    elif choice == 3:
        return _setup_shortcut(config)
    elif choice == 4:
        config["tracker"]["type"] = None
        click.echo("Ticket tracking disabled.")
        return True
    else:
        click.echo("Invalid choice")
        return False


def _setup_linear(config: dict[str, Any]) -> bool:
    """Set up Linear integration."""
    click.echo("\n--- Linear Setup ---")
    click.echo()
    click.echo("To get your Linear API key:")
    click.echo("  1. Go to Linear Settings > API")
    click.echo("  2. Create a new Personal API Key")
    click.echo("  3. Add to .env.local: LINEAR_API_KEY=lin_api_xxxxx")
    click.echo()

    # Check if already configured
    if os.environ.get("LINEAR_API_KEY"):
        click.echo("LINEAR_API_KEY detected in environment!")
    else:
        click.echo("Note: Add LINEAR_API_KEY to .env.local before using.")

    # Configure team
    click.echo()
    team_id = click.prompt(
        "Linear Team ID (optional, press Enter to skip)",
        default="",
        show_default=False,
    )

    workspace = click.prompt(
        "Linear Workspace slug (optional)",
        default="",
        show_default=False,
    )

    config["tracker"]["type"] = "linear"
    config["tracker"]["config"] = {
        "team_id": team_id if team_id else None,
        "workspace": workspace if workspace else None,
    }

    click.echo("\nLinear configured successfully!")

    # Prompt to enable native GitHub integration
    click.echo()
    click.echo("+" + "-" * 58 + "+")
    click.echo("|  Enable Linear's GitHub Integration (Recommended)        |")
    click.echo("+" + "-" * 58 + "+")
    click.echo("|                                                          |")
    click.echo("|  Linear's native integration automatically:              |")
    click.echo("|  - Links PRs to tickets based on branch names            |")
    click.echo("|  - Shows PR status in Linear                             |")
    click.echo("|  - Moves tickets to Done when PRs are merged             |")
    click.echo("|                                                          |")
    click.echo("|  Setup: Linear Settings > Integrations > GitHub          |")
    click.echo("|  Guide: recipes/tickets/linear-github-integration.md     |")
    click.echo("|                                                          |")
    click.echo("+" + "-" * 58 + "+")
    click.echo()

    if click.confirm("Will you use Linear's native GitHub integration?", default=True):
        config["tracker"]["config"]["github_integration"] = "native"
        click.echo()
        click.echo("To enable the integration:")
        click.echo("  1. Go to: https://linear.app/settings/integrations/github")
        click.echo("  2. Click 'Connect GitHub'")
        click.echo("  3. Authorize Linear to access your repos")
        click.echo("  4. Enable auto-close on merge (recommended)")
        click.echo()
        click.echo("See recipes/tickets/linear-github-integration.md for full guide.")
        click.echo()
        click.echo("Note: The fallback workflows (pr-opened.yml, pr-merged.yml) are")
        click.echo("      still available if you need them later.")
    else:
        config["tracker"]["config"]["github_integration"] = "fallback"
        click.echo()
        click.echo("Using fallback GitHub Actions workflows.")
        click.echo("Required: Add LINEAR_API_KEY as a repository secret.")
        click.echo("See: recipes/workflows/pr-opened-linear.md")

    # Offer to sync labels from Linear
    _try_sync_labels(config, "linear")

    return True


def _setup_github_issues(config: dict[str, Any]) -> bool:
    """Set up GitHub Issues integration."""
    import subprocess

    click.echo("\n--- GitHub Issues Setup ---")
    click.echo()

    # Check gh CLI is installed
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True, timeout=10)
    except (subprocess.CalledProcessError, FileNotFoundError):
        click.echo("Error: gh CLI is not installed.")
        click.echo("Install from: https://cli.github.com/")
        return False

    # Check gh is authenticated
    result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        click.echo("gh CLI is authenticated!")
    else:
        click.echo("gh CLI is not authenticated.")
        click.echo("Run: gh auth login")
        if not click.confirm("Continue anyway?", default=False):
            return False

    # Detect repo
    repo = ""
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode == 0 and result.stdout.strip():
        detected_repo = result.stdout.strip()
        click.echo(f"Detected repository: {detected_repo}")
        if click.confirm("Use this repository?", default=True):
            repo = detected_repo

    if not repo:
        repo = click.prompt("GitHub repository (owner/repo)", default="")

    config["tracker"]["type"] = "github"
    config["tracker"]["config"] = {
        "repo": repo if repo else None,
    }

    click.echo("\nGitHub Issues configured successfully!")
    click.echo()
    click.echo("No API keys needed - gh CLI handles authentication.")
    click.echo("All bin/ticket commands will use GitHub Issues.")

    # Offer to sync labels from GitHub
    _try_sync_labels(config, "github", repo=repo)

    return True


def _try_sync_labels(config: dict[str, Any], tracker_type: str, **kwargs: Any) -> None:
    """Attempt to sync labels from the tracker into the config dict.

    Updates config["labels"] in-place so the caller's save_config() persists
    the synced labels. This is a best-effort operation — if it fails (no API
    key yet, network issues, etc.), we skip and let the user sync later.
    """
    api_key = os.environ.get("LINEAR_API_KEY") if tracker_type == "linear" else None
    team_id = config.get("tracker", {}).get("config", {}).get("team_id")

    # For Linear, we need an API key to fetch labels
    if tracker_type == "linear" and not api_key:
        click.echo()
        click.echo("Tip: After adding LINEAR_API_KEY to .env.local, run:")
        click.echo("  bin/vibe sync-labels")
        click.echo("to populate config.json with your team's actual labels.")
        return

    try:
        from lib.vibe.label_sync import categorize_labels

        tracker: TrackerBase
        if tracker_type == "linear":
            from lib.vibe.trackers.linear import LinearTracker

            tracker = LinearTracker(api_key=api_key, team_id=team_id)
        elif tracker_type == "github":
            from lib.vibe.trackers.github_issues import GitHubIssuesTracker

            tracker = GitHubIssuesTracker(repo=kwargs.get("repo"))
        else:
            return

        click.echo()
        click.echo("Syncing labels from your team...")
        tracker_labels = tracker.list_labels()
        existing_labels = config.get("labels", {})
        new_labels = categorize_labels(tracker_labels, existing_labels)

        # Update config in-place so the wizard's save_config() persists it
        config["labels"] = new_labels

        if tracker_labels:
            area_labels = new_labels.get("area", [])
            click.echo(f"Synced {len(tracker_labels)} labels from {tracker_type}.")
            if area_labels:
                click.echo(f"  Area labels: {', '.join(area_labels)}")
        else:
            click.echo("No labels found in tracker. Using defaults.")
    except Exception:  # noqa: BLE001
        click.echo("Could not sync labels (will use defaults).")
        click.echo("Run 'bin/vibe sync-labels' later to sync from your tracker.")


def _setup_shortcut(config: dict[str, Any]) -> bool:
    """Set up Shortcut integration (stub)."""
    click.echo("\n--- Shortcut Setup ---")
    click.echo()
    click.echo("⚠️  Shortcut integration is not yet implemented.")
    click.echo("See GitHub issue #1 for tracking.")
    click.echo()
    click.echo("For now, you can:")
    click.echo("  1. Use Linear instead")
    click.echo("  2. Skip ticket tracking and add manually")
    click.echo()

    if click.confirm("Configure as placeholder (will not work yet)?", default=False):
        config["tracker"]["type"] = "shortcut"
        config["tracker"]["config"] = {
            "api_token": None,
            "workspace": None,
            "_stub": True,
        }
        click.echo("\nShortcut configured as placeholder.")
        return True

    return False
