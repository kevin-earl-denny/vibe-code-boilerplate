"""Main CLI entry point for vibe commands."""

import os
import re
import subprocess as _subprocess
import sys
from pathlib import Path

import click
import requests

from lib.vibe.cli.figma import figma
from lib.vibe.cli.secrets import main as secrets_group
from lib.vibe.doctor import print_results, run_doctor
from lib.vibe.trackers.base import TrackerBase
from lib.vibe.version import bump_version, get_version, write_version
from lib.vibe.wizards.setup import run_individual_wizard, run_setup

# Auto-load .env files at startup (unless disabled)
if os.environ.get("VIBE_NO_DOTENV") != "1":
    from lib.vibe.env import auto_load_env

    auto_load_env(verbose=os.environ.get("VIBE_VERBOSE") == "1")


@click.group()
@click.version_option(version=get_version(), prog_name="vibe")
def main() -> None:
    """Vibe Code Boilerplate - AI-assisted development workflows."""
    try:
        from lib.vibe.update_check import check_for_update, format_update_notice

        update_info = check_for_update()
        if update_info:
            click.echo(format_update_notice(update_info), err=True)
    except Exception:  # noqa: BLE001
        pass  # Never let update check break the CLI


@main.command("version")
def version_cmd() -> None:
    """Print the current version."""
    click.echo(get_version())


@main.command()
@click.argument("bump_type", type=click.Choice(["patch", "minor"]))
def bump(bump_type: str) -> None:
    """Bump the project version (patch or minor)."""
    current = get_version()
    new = bump_version(current, bump_type)
    write_version(new)
    click.echo(f"{current} → {new}")


@main.command()
@click.option("--skip", is_flag=True, help="Dismiss the update notice for 7 days")
@click.option("--force", "-f", is_flag=True, help="Force check even if recently checked")
def update(skip: bool, force: bool) -> None:
    """Check for and apply boilerplate updates."""
    import subprocess

    from lib.vibe.update_check import check_for_update, skip_update_check

    if skip:
        skip_update_check()
        click.echo("Update notice dismissed for 7 days.")
        return

    click.echo("Checking for boilerplate updates...")
    update_info = check_for_update(force=True)

    if not update_info:
        click.echo(f"Already up to date (v{get_version()}).")
        return

    current = update_info["current_version"]
    upstream = update_info["upstream_version"]
    click.echo(f"Update available: {current} -> {upstream}")

    if not click.confirm("Create a PR to sync the latest boilerplate?"):
        return

    # Create branch
    branch_name = f"chore/boilerplate-update-{upstream}"
    try:
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        click.echo(
            f"Error: Could not create branch '{branch_name}'. It may already exist.",
            err=True,
        )
        sys.exit(1)

    # Fetch and apply the latest boilerplate files
    # Download VERSION from upstream and update local
    write_version(upstream)

    # Run retrofit to sync boilerplate structure
    try:
        subprocess.run(
            ["bin/vibe", "retrofit", "--auto-only"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        pass  # retrofit may not apply anything, that's fine

    # Commit changes
    try:
        subprocess.run(["git", "add", "-A"], check=True, capture_output=True)
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True,
        )
        if result.returncode == 0:
            click.echo("No file changes detected. Version updated.")
            # Still commit the VERSION change
            subprocess.run(["git", "add", "VERSION"], check=True, capture_output=True)
            result = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                capture_output=True,
            )
            if result.returncode == 0:
                click.echo("Already at latest version. No changes needed.")
                subprocess.run(["git", "checkout", "-"], capture_output=True)
                subprocess.run(["git", "branch", "-D", branch_name], capture_output=True)
                return

        subprocess.run(
            ["git", "commit", "-m", f"chore: sync boilerplate to v{upstream}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        click.echo(f"Error committing changes: {e}", err=True)
        sys.exit(1)

    # Push and create PR
    try:
        subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        click.echo(f"Error pushing branch: {e}", err=True)
        sys.exit(1)

    # Get repo info for gh pr create
    from lib.vibe.config import load_config

    config = load_config()
    owner = config.get("github", {}).get("owner", "")
    repo = config.get("github", {}).get("repo", "")

    try:
        pr_result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--title",
                f"chore: sync boilerplate to v{upstream}",
                "--body",
                f"## Summary\n- Syncs boilerplate from v{current} to v{upstream}\n\n"
                f"Auto-generated by `bin/vibe update`.",
            ]
            + (["--repo", f"{owner}/{repo}"] if owner and repo else []),
            check=True,
            capture_output=True,
            text=True,
        )
        click.echo(f"PR created: {pr_result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        click.echo(f"Error creating PR: {e.stderr}", err=True)
        click.echo("Branch pushed. Create PR manually.", err=True)

    # Switch back to previous branch
    subprocess.run(["git", "checkout", "-"], capture_output=True)


@main.command()
@click.option("--force", "-f", is_flag=True, help="Force reconfiguration")
@click.option(
    "--wizard",
    "-w",
    help="Run a specific wizard (github, tracker, branch, env, vercel, fly, supabase, neon, database, sentry, playwright)",
)
@click.option("--quick", "-q", is_flag=True, help="Quick setup with sensible defaults, no prompts")
def setup(force: bool, wizard: str | None, quick: bool) -> None:
    """Run the setup wizard to configure your project.

    Use --quick for a fast setup (< 1 minute) with sensible defaults and no
    prompts. Perfect for trying out the boilerplate or when you want to
    configure integrations later.
    """
    if wizard:
        success = run_individual_wizard(wizard)
    elif quick:
        success = run_setup(force=force, quick=True)
    else:
        success = run_setup(force=force)

    sys.exit(0 if success else 1)


@main.command()
@click.option("--verbose", "-v", is_flag=True, help="Show verbose output")
@click.option("--live", "-l", is_flag=True, help="Run live integration checks (API calls)")
def doctor(verbose: bool, live: bool) -> None:
    """Check project health and configuration.

    Use --live to perform actual API calls and verify that integrations
    are working (e.g., test Linear API key, check Vercel auth).
    """
    results = run_doctor(verbose=verbose, live_checks=live)
    sys.exit(print_results(results))


@main.command("sync-labels")
@click.option("--dry-run", is_flag=True, help="Show what would change without saving")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def sync_labels(dry_run: bool, as_json: bool) -> None:
    """Sync labels from your ticket tracker into .vibe/config.json.

    Fetches the team's actual labels from Linear (or GitHub/Shortcut) and
    updates the labels section in config.json. Labels are automatically
    categorized into type, risk, area, and special buckets.

    Use --dry-run to preview changes without saving.
    """
    import json as _json

    from lib.vibe.config import load_config
    from lib.vibe.label_sync import sync_labels_to_config
    from lib.vibe.ui.components import Spinner

    config = load_config()
    tracker_type = config.get("tracker", {}).get("type")
    tracker_config = config.get("tracker", {}).get("config", {})

    if not tracker_type:
        click.echo("No tracker configured. Run 'bin/vibe setup -w tracker' first.", err=True)
        sys.exit(1)

    # Build the tracker instance
    tracker: TrackerBase
    if tracker_type == "linear":
        if not os.environ.get("LINEAR_API_KEY"):
            click.echo("LINEAR_API_KEY not set. Add it to .env.local first.", err=True)
            sys.exit(1)
        from lib.vibe.trackers.linear import LinearTracker

        tracker = LinearTracker(team_id=tracker_config.get("team_id"))
    elif tracker_type == "github":
        from lib.vibe.trackers.github_issues import GitHubIssuesTracker

        tracker = GitHubIssuesTracker(repo=tracker_config.get("repo"))
    elif tracker_type == "shortcut":
        from lib.vibe.trackers.shortcut import ShortcutTracker

        tracker = ShortcutTracker()
    else:
        click.echo(f"Unsupported tracker type: {tracker_type}", err=True)
        sys.exit(1)

    if not hasattr(tracker, "list_labels"):
        click.echo(f"Label syncing is not supported by the {tracker_type} tracker.", err=True)
        sys.exit(1)

    with Spinner(f"Fetching labels from {tracker_type}"):
        try:
            result = sync_labels_to_config(tracker, dry_run=dry_run)
        except Exception as e:
            click.echo(f"\nFailed to sync labels: {e}", err=True)
            sys.exit(1)

    if as_json:
        click.echo(_json.dumps(result, indent=2))
        return

    count = result["tracker_count"]
    labels = result["labels"]

    click.echo(f"\nFetched {count} labels from {tracker_type}.")
    click.echo()

    for category in ["type", "risk", "area", "special"]:
        items = labels.get(category, [])
        click.echo(f"  {category.title():8s} ({len(items)}): {', '.join(items)}")

    click.echo()

    if dry_run:
        if result["changed"]:
            click.echo("Changes detected (dry run — not saved).")
            click.echo("Run without --dry-run to apply.")
        else:
            click.echo("No changes needed.")
    elif result["changed"]:
        click.echo("Labels updated in .vibe/config.json")
    else:
        click.echo("Labels already up to date.")


@main.command()
@click.argument("ticket_id")
def do(ticket_id: str) -> None:
    """Start working on a ticket (creates worktree and branch from latest main)."""
    import subprocess

    from lib.vibe.config import load_config
    from lib.vibe.git.branches import format_branch_name, get_main_branch
    from lib.vibe.git.worktrees import create_worktree, get_primary_repo_root
    from lib.vibe.state import record_ticket_branch
    from lib.vibe.trackers.github_issues import GitHubIssuesTracker
    from lib.vibe.trackers.linear import LinearTracker
    from lib.vibe.ui.components import Spinner

    config = load_config()
    tracker_type = config.get("tracker", {}).get("type")
    tracker_config = config.get("tracker", {}).get("config", {})

    # Get ticket info if tracker configured
    title = None
    if tracker_type == "linear":
        linear = LinearTracker()
        with Spinner(f"Fetching ticket {ticket_id}"):
            ticket = linear.get_ticket(ticket_id)
        if ticket:
            title = ticket.title
            click.echo(f"Found ticket: {ticket.title}")
    elif tracker_type == "github":
        gh_tracker = GitHubIssuesTracker(repo=tracker_config.get("repo"))
        with Spinner(f"Fetching issue {ticket_id}"):
            ticket = gh_tracker.get_ticket(ticket_id)
        if ticket:
            title = ticket.title
            click.echo(f"Found issue: {ticket.title}")

    # Create branch name
    branch_name = format_branch_name(ticket_id, title)
    click.echo(f"Branch: {branch_name}")

    # Fetch latest main so new branch is based on origin/main
    main_branch = get_main_branch()
    try:
        subprocess.run(
            ["git", "fetch", "origin", main_branch],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        click.echo(f"Warning: could not fetch origin/{main_branch}: {e}", err=True)

    # Create worktree from origin/main so branch is rebased to latest main
    origin_main = f"origin/{main_branch}"
    try:
        worktree = create_worktree(branch_name, base_branch=origin_main)
        click.echo(f"Worktree created at: {worktree.path}")
        click.echo(f"\nTo start working:\n  cd {worktree.path}")

        # Record ticket-to-branch mapping for duplicate PR detection
        repo_root = get_primary_repo_root()
        record_ticket_branch(
            ticket_id, branch_name, worktree_path=worktree.path, base_path=repo_root
        )
    except (subprocess.CalledProcessError, OSError, RuntimeError) as e:
        click.echo(f"Failed to create worktree: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--dry-run", is_flag=True, help="Show what would be removed without removing")
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def cleanup(dry_run: bool, force: bool) -> None:
    """Clean up worktrees for branches that have been merged.

    Detects worktrees whose PRs have been merged and removes them along
    with their local branches. Runs `bin/vibe doctor` afterward to sync state.
    """
    import json as _json
    import subprocess

    # Get list of worktrees
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        click.echo("Failed to list worktrees.", err=True)
        sys.exit(1)

    # Parse worktrees
    main_worktree = str(Path.cwd().resolve())
    worktrees: list[dict[str, str]] = []
    current_wt: dict[str, str] = {}

    for line in result.stdout.split("\n"):
        if line.startswith("worktree "):
            if current_wt:
                worktrees.append(current_wt)
            current_wt = {"path": line.split(" ", 1)[1]}
        elif line.startswith("branch "):
            current_wt["branch"] = line.split(" ", 1)[1].replace("refs/heads/", "")
        elif line == "":
            if current_wt:
                worktrees.append(current_wt)
            current_wt = {}
    if current_wt:
        worktrees.append(current_wt)

    # Filter out main worktree
    feature_worktrees = [
        wt
        for wt in worktrees
        if wt.get("path") and str(Path(wt["path"]).resolve()) != main_worktree
    ]

    if not feature_worktrees:
        click.echo("No feature worktrees found. Nothing to clean up.")
        return

    # Check each worktree for merged status
    merged: list[dict[str, object]] = []
    active: list[dict[str, str]] = []

    for wt in feature_worktrees:
        branch = wt.get("branch", "")
        if not branch:
            continue

        # Check if branch has a merged PR
        try:
            pr_result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--head",
                    branch,
                    "--state",
                    "merged",
                    "--json",
                    "number,title",
                    "--limit",
                    "1",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if pr_result.returncode == 0 and pr_result.stdout.strip() not in ("", "[]"):
                prs = _json.loads(pr_result.stdout)
                if prs:
                    merged_wt: dict[str, object] = {
                        **wt,
                        "pr_number": prs[0].get("number"),
                        "pr_title": prs[0].get("title", ""),
                    }
                    merged.append(merged_wt)
                    continue
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Check if branch was deleted on remote
        try:
            remote_check = subprocess.run(
                ["git", "ls-remote", "--heads", "origin", branch],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if remote_check.returncode == 0 and not remote_check.stdout.strip():
                # Branch deleted on remote - likely merged
                merged_wt = {
                    **wt,
                    "pr_number": None,
                    "pr_title": "(branch deleted on remote)",
                }
                merged.append(merged_wt)
                continue
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        active.append(wt)

    # Report findings
    if merged:
        click.echo(f"\nMerged (safe to remove): {len(merged)}")
        for mwt in merged:
            pr_info = f" (PR #{mwt.get('pr_number')})" if mwt.get("pr_number") else ""
            click.echo(f"  {mwt.get('branch', 'unknown')}{pr_info} — {mwt['path']}")

    if active:
        click.echo(f"\nStill active: {len(active)}")
        for awt in active:
            click.echo(f"  {awt.get('branch', 'unknown')} — {awt['path']}")

    if not merged:
        click.echo("\nNo merged worktrees found. Nothing to clean up.")
        return

    if dry_run:
        click.echo(f"\nDry run: would remove {len(merged)} worktree(s).")
        return

    # Confirm
    if not force:
        if not click.confirm(f"\nRemove {len(merged)} merged worktree(s)?", default=True):
            click.echo("Cancelled.")
            return

    # Remove merged worktrees
    removed = 0
    for mwt in merged:
        branch = str(mwt.get("branch", ""))
        path = mwt.get("path", "")

        # Check for uncommitted changes
        try:
            status_result = subprocess.run(
                ["git", "-C", str(path), "status", "--porcelain"],
                capture_output=True,
                text=True,
            )
            if status_result.stdout.strip():
                click.echo(f"  Skipping {branch} (has uncommitted changes)")
                continue
        except subprocess.CalledProcessError:
            pass

        # Remove worktree
        try:
            subprocess.run(
                ["git", "worktree", "remove", str(path)],
                check=True,
                capture_output=True,
                text=True,
            )
            click.echo(f"  Removed worktree: {path}")
        except subprocess.CalledProcessError as e:
            click.echo(f"  Failed to remove worktree {path}: {e.stderr}", err=True)
            continue

        # Delete local branch
        try:
            subprocess.run(
                ["git", "branch", "-d", str(branch)],
                check=True,
                capture_output=True,
                text=True,
            )
            click.echo(f"  Deleted branch: {branch}")
        except subprocess.CalledProcessError:
            # Try force delete if branch wasn't fully merged according to git
            try:
                subprocess.run(
                    ["git", "branch", "-D", str(branch)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                click.echo(f"  Deleted branch: {branch} (force)")
            except subprocess.CalledProcessError as e:
                click.echo(f"  Could not delete branch {branch}: {e.stderr}", err=True)

        removed += 1

    click.echo(f"\nCleaned up {removed} worktree(s).")

    # Run doctor to sync state
    click.echo("\nRunning doctor to sync state...")
    doctor_results = run_doctor()
    # Just show a summary, not full results
    passed = sum(1 for r in doctor_results if r.status.value == "\u2713")
    click.echo(f"Doctor: {passed}/{len(doctor_results)} checks passed.")


def _get_first_commit_headline(main_branch: str = "main") -> str | None:
    """Get the first commit message headline on this branch (relative to origin/<main_branch>)."""
    try:
        result = _subprocess.run(
            ["git", "log", f"origin/{main_branch}..HEAD", "--format=%s", "--reverse"],
            capture_output=True,
            text=True,
            check=True,
        )
        lines = result.stdout.strip().splitlines()
        if lines:
            return lines[0].strip()
    except _subprocess.CalledProcessError:
        pass
    return None


def _derive_pr_title(branch: str, config: dict) -> str:
    """Derive a meaningful PR title from branch name, tracker, or commit history.

    Priority order:
    1. Extract ticket ID from branch → fetch title from tracker → "TICKET-ID: Title"
    2. No ticket ID but valid branch → first commit headline on branch
    3. worktree-agent-* branch → warn and use first commit headline
    4. Raw branch name as absolute last resort
    """
    main_branch = config.get("branching", {}).get("main_branch", "main")

    # Cache the first-commit headline so we only shell out once
    headline = _get_first_commit_headline(main_branch)

    # Step 1: Try to extract a ticket ID from the branch name
    ticket_match = re.search(r"([A-Z]+-\d+)", branch)
    ticket_id = ticket_match.group(1) if ticket_match else None

    # Step 2: If we have a ticket ID, try to fetch the title from the tracker
    if ticket_id:
        tracker_type = config.get("tracker", {}).get("type")
        if tracker_type:
            try:
                if tracker_type == "linear":
                    from lib.vibe.trackers.linear import LinearTracker

                    linear_tracker = LinearTracker()
                    ticket = linear_tracker.get_ticket(ticket_id)
                    if ticket and ticket.title:
                        return f"{ticket_id}: {ticket.title}"
                elif tracker_type == "shortcut":
                    from lib.vibe.trackers.shortcut import ShortcutTracker

                    shortcut_tracker = ShortcutTracker()
                    ticket = shortcut_tracker.get_ticket(ticket_id)
                    if ticket and ticket.title:
                        return f"{ticket_id}: {ticket.title}"
            except (requests.RequestException, RuntimeError):
                # Tracker API failed; fall through to commit-based title
                pass

        # Tracker not configured or API failed — use ticket ID + first commit
        if headline:
            return f"{ticket_id}: {headline}"
        # Last resort with ticket ID
        return ticket_id

    # Step 3: Handle worktree-agent-* branches (no meaningful ticket ID)
    if re.match(r"^worktree-agent-", branch):
        click.echo(
            "Warning: branch name looks auto-generated (worktree-agent-*). "
            "Using first commit message as PR title.",
            err=True,
        )
        if headline:
            return headline

    # Step 4: No ticket ID — try first commit headline for any branch
    if headline:
        return headline

    # Step 5: Absolute last resort — raw branch name
    return branch


def _extract_ticket_id(branch: str) -> str | None:
    """Extract a ticket ID (e.g. PROJ-123) from a branch name."""
    ticket_match = re.search(r"([A-Z]+-\d+)", branch)
    return ticket_match.group(1) if ticket_match else None


def _check_existing_prs_for_ticket(ticket_id: str) -> list[dict[str, object]]:
    """Query GitHub for open or recently-merged PRs referencing *ticket_id*.

    Returns a list of dicts with ``number``, ``title``, ``state``, and ``url`` keys.
    An empty list means no matching PRs were found (or ``gh`` is unavailable).
    """
    import json as _json

    try:
        result = _subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--search",
                ticket_id,
                "--state",
                "all",
                "--json",
                "number,title,state,url",
                "--limit",
                "20",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            prs: list[dict[str, object]] = _json.loads(result.stdout)
            # Filter to only PRs whose title actually contains the ticket ID
            return [
                pr_item
                for pr_item in prs
                if ticket_id.upper() in str(pr_item.get("title", "")).upper()
            ]
    except (FileNotFoundError, _subprocess.TimeoutExpired, _json.JSONDecodeError):
        pass
    return []


def _check_local_state_for_ticket_conflicts(
    ticket_id: str, current_branch: str
) -> list[dict[str, str]]:
    """Check .vibe/local_state.json for other branches associated with *ticket_id*.

    Returns recorded branches that match the ticket but differ from *current_branch*.
    """
    from lib.vibe.state import get_branches_for_ticket

    recorded = get_branches_for_ticket(ticket_id)
    return [
        entry for entry in recorded if entry.get("branch") and entry["branch"] != current_branch
    ]


def _warn_duplicate_prs(ticket_id: str, branch: str, *, skip_confirmation: bool = False) -> bool:
    """Run duplicate-PR checks and warn the user.

    Returns ``True`` if it is safe to proceed (no duplicates found, or user
    confirmed).  Returns ``False`` if the user chose to abort.
    """
    should_abort = False

    # Check 1: Existing GitHub PRs for this ticket
    existing_prs = _check_existing_prs_for_ticket(ticket_id)
    if existing_prs:
        merged_prs = [p for p in existing_prs if p.get("state") == "MERGED"]
        open_prs = [p for p in existing_prs if p.get("state") == "OPEN"]

        if merged_prs:
            click.echo(
                f"\n** WARNING: Found {len(merged_prs)} MERGED PR(s) for ticket "
                f"{ticket_id}. This may be duplicate work. **",
                err=True,
            )
            for p in merged_prs:
                click.echo(
                    f"  - PR #{p.get('number')}: {p.get('title')} ({p.get('url')})",
                    err=True,
                )
            should_abort = True

        if open_prs:
            click.echo(
                f"\nWarning: Found {len(open_prs)} OPEN PR(s) for ticket {ticket_id}:",
                err=True,
            )
            for p in open_prs:
                click.echo(
                    f"  - PR #{p.get('number')}: {p.get('title')} ({p.get('url')})",
                    err=True,
                )
            should_abort = True

    # Check 2: Local state — other branches for the same ticket
    conflicts = _check_local_state_for_ticket_conflicts(ticket_id, branch)
    if conflicts:
        click.echo(
            f"\nWarning: Another branch is already recorded for ticket {ticket_id}:",
            err=True,
        )
        for c in conflicts:
            click.echo(
                f"  - Branch: {c.get('branch')} (worktree: {c.get('worktree_path', 'unknown')})",
                err=True,
            )
        should_abort = True

    if should_abort and not skip_confirmation:
        if not click.confirm("\nA PR may already exist for this ticket. Create a new PR anyway?"):
            return False

    return True


@main.command()
@click.option("--title", "-t", help="PR title (default: branch name or branch + first commit line)")
@click.option("--body", "-b", help="PR body (default: use template)")
@click.option("--web", is_flag=True, help="Open PR form in the browser")
def pr(title: str | None, body: str | None, web: bool) -> None:
    """Open a pull request for the current branch (run from your worktree when done)."""
    import subprocess

    from lib.vibe.config import load_config
    from lib.vibe.git.branches import current_branch, get_main_branch

    main_branch = get_main_branch()
    branch = current_branch()
    if branch == main_branch:
        click.echo(
            f"Cannot open PR from {main_branch}. Check out your feature branch first.", err=True
        )
        sys.exit(1)

    config = load_config()

    # Check for duplicate PRs before creating a new one
    ticket_id = _extract_ticket_id(branch)
    if ticket_id:
        if not _warn_duplicate_prs(ticket_id, branch):
            click.echo("PR creation cancelled.")
            sys.exit(0)

    args = ["gh", "pr", "create"]
    if title:
        args.extend(["--title", title])
    else:
        derived_title = _derive_pr_title(branch, config)
        args.extend(["--title", derived_title])
    if body:
        args.extend(["--body", body])
    else:
        # Use PR template if it exists
        template = Path(".github/PULL_REQUEST_TEMPLATE.md")
        if template.exists():
            args.extend(["--body-file", str(template)])
    if web:
        args.append("--web")

    try:
        result = subprocess.run(args, check=True, capture_output=True, text=True)
        pr_url = result.stdout.strip()
        click.echo("PR created.")
        if pr_url:
            click.echo(pr_url)

        # Best-effort: auto-link PR to the tracker ticket
        _autolink_pr_to_ticket(branch, pr_url, config)
    except subprocess.CalledProcessError as e:
        click.echo(f"Failed to create PR: {e}", err=True)
        if e.stderr:
            click.echo(e.stderr, err=True)
        click.echo("Run: gh pr create")
        sys.exit(1)
    except FileNotFoundError:
        click.echo("gh CLI not found. Install it: https://cli.github.com/")
        click.echo("Then run: gh pr create")
        sys.exit(1)


def _autolink_pr_to_ticket(branch: str, pr_url: str, config: dict) -> None:
    """Best-effort: add a comment on the tracker ticket linking to the PR.

    Extracts the ticket ID from the branch name, then posts a comment with
    the PR URL if a tracker is configured. Failures are logged but never
    prevent the PR from being created.
    """
    if not pr_url:
        return

    ticket_match = re.search(r"([A-Z]+-\d+)", branch)
    if not ticket_match:
        return

    ticket_id = ticket_match.group(1)
    tracker_type = config.get("tracker", {}).get("type")
    if not tracker_type:
        return

    try:
        from lib.vibe.trackers.base import TrackerBase

        tracker: TrackerBase | None = None
        if tracker_type == "linear":
            from lib.vibe.trackers.linear import LinearTracker

            tracker = LinearTracker(
                team_id=config.get("tracker", {}).get("config", {}).get("team_id")
            )
        elif tracker_type == "shortcut":
            from lib.vibe.trackers.shortcut import ShortcutTracker

            tracker = ShortcutTracker()

        if tracker is None:
            return

        comment_body = f"PR opened: {pr_url}"
        tracker.comment_ticket(ticket_id, comment_body)
        click.echo(f"Linked PR to ticket {ticket_id}.")
    except Exception:  # noqa: BLE001
        # Best-effort — never fail the PR creation because of a tracker issue
        click.echo(f"Note: Could not auto-link PR to ticket {ticket_id}.", err=True)


# NOTE: These URLs point to the vibe-code-boilerplate repository itself, NOT the user's
# project. They're used for reporting bugs/issues with the boilerplate (broken recipes,
# CLAUDE.md errors, etc.). Users who fork the boilerplate keep these URLs so they can
# report upstream issues. Project-specific issues should use the project's own GitHub repo.
BOILERPLATE_ISSUES_URL = "https://github.com/kdenny/vibe-code-boilerplate/issues"
BOILERPLATE_NEW_ISSUE_URL = "https://github.com/kdenny/vibe-code-boilerplate/issues/new"


@main.command()
@click.option("--title", "-t", help="Pre-fill issue title")
@click.option("--body", "-b", help="Pre-fill issue body (or path to file with body)")
@click.option("--print-only", is_flag=True, help="Print URL only, do not open browser")
def boilerplate_issue(title: str | None, body: str | None, print_only: bool) -> None:
    """Open the boilerplate repo's new-issue page (for reporting broken CLAUDE.md or recipes)."""
    from urllib.parse import quote

    try:
        from lib.vibe.config import load_config

        config = load_config()
        base = (config.get("boilerplate") or {}).get("issues_url") or BOILERPLATE_ISSUES_URL
        new_issue = base.rstrip("/").replace("/issues", "") + "/issues/new"
    except (OSError, KeyError, RuntimeError):
        new_issue = BOILERPLATE_NEW_ISSUE_URL

    params = []
    if title:
        params.append(f"title={quote(title)}")
    if body:
        if body.startswith("@") or "/" in body:
            try:
                with open(body.lstrip("@")) as f:
                    body = f.read()
            except OSError:
                pass
        params.append(f"body={quote(body)}")
    if params:
        new_issue += "?" + "&".join(params)

    if print_only:
        click.echo(new_issue)
        return

    try:
        import webbrowser

        webbrowser.open(new_issue)
        click.echo("Opened boilerplate repo new-issue page in your browser.")
        click.echo("If it did not open, use: " + new_issue)
    except OSError:
        click.echo("Could not open browser. File an issue manually at:")
        click.echo(new_issue)


# Register secrets commands from lib.vibe.cli.secrets
main.add_command(secrets_group, "secrets")


@main.command("init-actions")
@click.option("--linear", is_flag=True, help="Include Linear integration workflows")
@click.option("--dry-run", is_flag=True, help="Preview changes without applying")
@click.option("--all", "include_all", is_flag=True, help="Include all available workflows")
@click.option("--interactive", "-i", is_flag=True, help="Interactive mode for workflow selection")
def init_actions(linear: bool, dry_run: bool, include_all: bool, interactive: bool) -> None:
    """Initialize GitHub Actions workflows, secrets, and labels.

    Sets up:
    - Core workflows (PR policy, security, lint, tests)
    - Required labels (risk levels, types)
    - Optionally: Linear integration workflows and secrets

    LINEAR_API_KEY is read from the environment variable, not a CLI flag.
    Set it before running: export LINEAR_API_KEY=lin_api_...

    Examples:

        bin/vibe init-actions                    # Core workflows only
        bin/vibe init-actions --linear           # Include Linear workflows
        bin/vibe init-actions --interactive      # Interactive workflow selection
        bin/vibe init-actions --dry-run          # Preview what would be done
    """
    from lib.vibe.github_actions import init_github_actions
    from lib.vibe.ui.components import MultiSelect

    linear_api_key = os.environ.get("LINEAR_API_KEY")

    # Interactive mode
    if interactive:
        click.echo("\n" + "=" * 50)
        click.echo("  Initialize GitHub Actions")
        click.echo("=" * 50)
        click.echo()

        workflow_select = MultiSelect(
            title="Select workflows to install:",
            options=[
                ("Core Workflows", "PR policy, security, lint, tests (recommended)", True),
                ("Linear Integration", "Sync PR status with Linear tickets", False),
                ("Shortcut Integration", "Sync PR status with Shortcut stories", False),
            ],
        )
        selected = workflow_select.show()

        if not selected:
            click.echo("No workflows selected. Cancelled.")
            return

        # Update flags based on selection
        if 2 in selected:
            linear = True
            if not linear_api_key:
                click.echo()
                click.echo("Linear integration requires LINEAR_API_KEY.")
                click.echo("Set it as an environment variable: export LINEAR_API_KEY=lin_api_...")
                if click.confirm("Enter LINEAR_API_KEY now?", default=True):
                    linear_api_key = click.prompt("LINEAR_API_KEY", hide_input=True)

    if dry_run:
        click.echo("Dry run - showing what would be done:\n")

    result = init_github_actions(
        include_linear=linear or include_all,
        linear_api_key=linear_api_key,
        dry_run=dry_run,
    )

    if result.workflows_copied:
        click.echo(f"Workflows {'would be ' if dry_run else ''}copied:")
        for wf in result.workflows_copied:
            click.echo(f"  - {wf}")
    else:
        click.echo("No new workflows to copy (already exist or none selected)")

    if result.labels_created:
        click.echo(f"\nLabels {'would be ' if dry_run else ''}created/updated:")
        for label in result.labels_created:
            click.echo(f"  - {label}")

    if result.secrets_set:
        click.echo(f"\nSecrets {'would be ' if dry_run else ''}set:")
        for secret in result.secrets_set:
            click.echo(f"  - {secret}")

    if result.errors:
        click.echo("\nErrors:")
        for error in result.errors:
            click.echo(f"  - {error}")

    if not dry_run:
        click.echo("\nGitHub Actions initialized!")
        click.echo("Run 'git add .github && git commit' to commit the workflows.")

    sys.exit(0 if result.success else 1)


@main.command("cors-check")
@click.argument("url")
@click.option("--origin", "-o", default="http://localhost:3000", help="Origin to test from")
@click.option("--method", "-m", default="GET", help="HTTP method to test")
@click.option("--header", "-H", multiple=True, help="Headers to include in preflight")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def cors_check(
    url: str, origin: str, method: str, header: tuple[str, ...], json_output: bool
) -> None:
    """Check CORS configuration for a URL.

    Diagnoses CORS issues by sending preflight and actual requests,
    then analyzing the response headers.

    Examples:

        bin/vibe cors-check https://api.example.com/users

        bin/vibe cors-check https://api.example.com/users -o http://myapp.com

        bin/vibe cors-check https://api.example.com/users -m POST -H Authorization
    """
    from lib.vibe.cors import check_cors, format_cors_result

    result = check_cors(
        url=url,
        origin=origin,
        method=method,
        headers=list(header) if header else None,
    )

    click.echo(format_cors_result(result, json_output=json_output))
    sys.exit(0 if result.success else 1)


@main.command()
@click.option("--dry-run", is_flag=True, help="Show what would be done without making changes")
@click.option("--auto", is_flag=True, help="Apply all auto-applicable actions without prompting")
@click.option("--analyze-only", is_flag=True, help="Only show analysis, don't apply any changes")
@click.option(
    "--interactive", "-i", is_flag=True, help="Interactive multi-select mode for choosing actions"
)
@click.option(
    "--json", "json_output", is_flag=True, help="Output results as JSON (for agent/script use)"
)
@click.option(
    "--boilerplate-path",
    "-b",
    type=click.Path(exists=True, path_type=Path),
    help="Path to boilerplate source (for copying workflows)",
)
def retrofit(
    dry_run: bool,
    auto: bool,
    analyze_only: bool,
    interactive: bool,
    json_output: bool,
    boilerplate_path: Path | None,
) -> None:
    """Apply boilerplate to an existing project (guided adoption)."""
    import json

    from lib.vibe.config import load_config
    from lib.vibe.retrofit.analyzer import ActionType, RetrofitAnalyzer
    from lib.vibe.retrofit.applier import RetrofitApplier
    from lib.vibe.retrofit.detector import ProjectDetector
    from lib.vibe.tools import require_interactive
    from lib.vibe.ui.components import MultiSelect, WhatNextFlow
    from lib.vibe.wizards.setup import run_individual_wizard

    # Check for interactive terminal if we'll need user input
    if not auto and not analyze_only and not json_output:
        ok, error = require_interactive("Retrofit")
        if not ok:
            click.echo(f"\n{error}")
            click.echo("\nTip: Use --auto to apply changes without prompting,")
            click.echo("     or --analyze-only to see what would be detected,")
            click.echo("     or --json for machine-readable output.")
            sys.exit(1)

    if not json_output:
        click.echo("=" * 60)
        click.echo("  Retrofit: Apply Boilerplate to Existing Project")
        click.echo("=" * 60)
        click.echo()

    # Step 1: Detect existing configuration
    if not json_output:
        click.echo("Analyzing project...")
    detector = ProjectDetector()
    profile = detector.detect_all()

    # Step 2: Generate retrofit plan
    analyzer = RetrofitAnalyzer(profile)
    plan = analyzer.analyze()

    # JSON output mode - return structured data for agents
    if json_output:
        output = {
            "profile": {
                "main_branch": profile.main_branch.value if profile.main_branch.detected else None,
                "branch_pattern": profile.branch_pattern.value
                if profile.branch_pattern.detected
                else None,
                "frontend_framework": profile.frontend_framework.value
                if profile.frontend_framework.detected
                else None,
                "backend_framework": profile.backend_framework.value
                if profile.backend_framework.detected
                else None,
                "test_framework": profile.test_framework.value
                if profile.test_framework.detected
                else None,
                "has_vibe_config": profile.has_vibe_config.detected,
            },
            "actions": [
                {
                    "name": a.name,
                    "description": a.description,
                    "type": a.action_type.value,
                    "auto_applicable": a.auto_applicable,
                    "priority": a.priority.value,
                }
                for a in plan.actions
            ],
            "conflicts": [
                {
                    "description": c.description,
                    "current": c.current_value,
                    "suggested": c.suggested_value,
                    "details": c.details,
                }
                for c in plan.conflicts
            ],
            "summary": {
                "total_actions": len(plan.actions),
                "auto_applicable": len(plan.auto_applicable_actions),
                "has_conflicts": len(plan.conflicts) > 0,
            },
        }
        click.echo(json.dumps(output, indent=2))
        return

    # Step 3: Show analysis summary
    click.echo()
    click.echo(analyzer.generate_summary(plan))

    if analyze_only:
        click.echo(
            "Analysis complete. Use --dry-run to preview changes or remove --analyze-only to apply."
        )
        return

    # Check for conflicts
    if plan.conflicts:
        click.echo("!" * 60)
        click.echo("  CONFLICTS DETECTED - Manual resolution required")
        click.echo("!" * 60)
        click.echo()
        for conflict in plan.conflicts:
            click.echo(f"  • {conflict.description}")
            click.echo(f"    Current: {conflict.current_value}")
            click.echo(f"    Suggested: {conflict.suggested_value}")
            click.echo(f"    {conflict.details}")
            click.echo()

    # Step 4: Apply changes
    if dry_run:
        click.echo("Dry run - showing what would be applied:")
        click.echo("-" * 40)

    applier = RetrofitApplier(
        project_path=Path.cwd(),
        boilerplate_path=boilerplate_path,
        dry_run=dry_run,
    )

    if auto:
        # Apply all auto-applicable actions without prompting
        click.echo("\nApplying auto-applicable actions...")
        results = applier.apply_plan(plan, auto_only=True, interactive=False)
    elif interactive:
        # Interactive multi-select mode
        applicable_actions = [
            a for a in plan.actions if a.action_type in (ActionType.ADOPT, ActionType.CONFIGURE)
        ]

        if not applicable_actions:
            click.echo("\nNo applicable actions found.")
            click.echo("Run 'bin/vibe setup' for manual configuration options.")
            return

        click.echo()
        multi_select = MultiSelect(
            title="Select actions to apply:",
            options=[(a.name, a.description, a.auto_applicable) for a in applicable_actions],
        )
        selected_indices = multi_select.show()

        if not selected_indices:
            click.echo("No actions selected. Retrofit cancelled.")
            return

        # Filter to only selected actions
        selected_actions = [applicable_actions[i - 1] for i in selected_indices]

        # Apply selected actions
        results = []
        for action in selected_actions:
            result = applier.apply_action(action)
            results.append(result)
            status = "PASS" if result.success else "FAIL"
            click.echo(f"  {status} {result.message}")
    else:
        # Default interactive mode (confirm all auto-applicable)
        if not plan.auto_applicable_actions:
            click.echo("\nNo auto-applicable actions found.")
            click.echo("Run 'bin/vibe setup' for manual configuration options.")
            return

        click.echo("\nThe following actions can be applied automatically:")
        for action in plan.auto_applicable_actions:
            click.echo(f"  • {action.description}")

        click.echo()
        if not click.confirm("Apply these changes?", default=True):
            click.echo("Retrofit cancelled.")
            return

        results = applier.apply_plan(plan, auto_only=True, interactive=True)

    # Step 5: Summary
    click.echo()
    click.echo("=" * 60)
    click.echo("  Retrofit Summary")
    click.echo("=" * 60)

    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    if successful:
        click.echo(f"\n✓ Applied {len(successful)} action(s):")
        for result in successful:
            click.echo(f"  • {result.message}")

    if failed:
        click.echo(f"\n✗ Failed {len(failed)} action(s):")
        for result in failed:
            click.echo(f"  • {result.action_name}: {result.message}")

    # Next steps
    click.echo("\nNext steps:")
    click.echo("  1. Run 'bin/vibe doctor' to verify configuration")
    click.echo("  2. Run 'bin/vibe setup -w tracker' to configure ticket tracking")
    click.echo("  3. Review .vibe/config.json and adjust settings as needed")
    click.echo("  4. Update CLAUDE.md with your project's context")

    # Show WhatNextFlow for natural wizard chaining
    config = load_config()
    what_next = WhatNextFlow("env", config)  # Use "env" as retrofit touches env/config
    next_wizard = what_next.show()
    if next_wizard:
        run_individual_wizard(next_wizard, show_what_next=True)


@main.command("generate-agent-instructions")
@click.option("--dry-run", is_flag=True, help="Show what would be generated without writing files")
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite files even if they have project-specific content",
)
@click.option(
    "--format",
    "-f",
    "formats",
    multiple=True,
    type=click.Choice(["claude", "cursor", "copilot", "all"]),
    default=["all"],
    help="Which formats to generate (default: all)",
)
@click.option(
    "--interactive", "-i", is_flag=True, help="Interactive mode - select formats with MultiSelect"
)
@click.option(
    "--source-dir",
    "-s",
    type=click.Path(exists=True, path_type=Path),
    default="agent_instructions",
    help="Source directory for instruction files",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    default=".",
    help="Output directory for generated files",
)
def generate_agent_instructions(
    dry_run: bool,
    force: bool,
    formats: tuple[str, ...],
    interactive: bool,
    source_dir: Path,
    output_dir: Path,
) -> None:
    """Generate assistant-specific instruction files from common spec.

    Reads instruction spec from agent_instructions/ and generates:
    - CLAUDE.md (Claude Code)
    - .cursor/rules (Cursor IDE)
    - .github/copilot-instructions.md (GitHub Copilot)

    This allows maintaining a single source of truth for agent instructions.
    """
    from lib.vibe.agents.generator import InstructionGenerator
    from lib.vibe.agents.spec import AssistantFormat, InstructionSpec
    from lib.vibe.ui.components import MultiSelect

    source_path = Path(source_dir)
    if not source_path.exists():
        click.secho(f"Source directory not found: {source_path}", fg="red", err=True)
        click.echo("Create agent_instructions/ with CORE.md, COMMANDS.md, WORKFLOW.md")
        sys.exit(1)

    # Determine which formats to generate
    format_map = {
        "claude": AssistantFormat.CLAUDE,
        "cursor": AssistantFormat.CURSOR,
        "copilot": AssistantFormat.COPILOT,
    }

    if interactive:
        # Interactive format selection
        click.echo("\n" + "=" * 50)
        click.echo("  Generate Agent Instructions")
        click.echo("=" * 50)
        click.echo()

        multi_select = MultiSelect(
            title="Select formats to generate:",
            options=[
                ("CLAUDE.md", "Claude Code instructions", True),
                (".cursor/rules", "Cursor IDE instructions", True),
                (".github/copilot-instructions.md", "GitHub Copilot instructions", False),
            ],
        )
        selected_indices = multi_select.show()

        if not selected_indices:
            click.echo("No formats selected. Cancelled.")
            return

        index_to_format = {
            1: AssistantFormat.CLAUDE,
            2: AssistantFormat.CURSOR,
            3: AssistantFormat.COPILOT,
        }
        selected_formats = [index_to_format[i] for i in selected_indices]
    elif "all" in formats:
        selected_formats = list(format_map.values())
    else:
        selected_formats = [format_map[f] for f in formats if f in format_map]

    # Load label categories from .vibe/config.json (if available)
    from lib.vibe.config import load_config

    config = load_config(output_dir if output_dir != Path(".") else None)
    config_labels: dict[str, list[str]] = config.get("labels", {})

    # Load spec from source files
    click.echo(f"Loading instruction spec from {source_path}/...")
    spec = InstructionSpec.from_files(source_path, config_labels=config_labels)

    click.echo(f"  - Loaded {len(spec.core_rules)} core rules")
    click.echo(f"  - Loaded {len(spec.commands)} commands")
    click.echo(f"  - Loaded {len(spec.workflows)} workflows")
    if spec.labels:
        label_count = sum(len(v) for v in spec.labels.values())
        click.echo(f"  - Loaded {label_count} labels from config")

    # Generate files
    generator = InstructionGenerator(spec)
    output_path = Path(output_dir)

    if dry_run:
        click.echo()
        click.secho("Dry run - would generate:", fg="yellow")
        for fmt in selected_formats:
            full_path = output_path / fmt.output_path
            click.echo(f"  {full_path} ({fmt.description})")
        return

    click.echo()
    click.secho("Generating instruction files...", fg="cyan")

    results = generator.generate_all(output_path, selected_formats, force=force)

    for format_name, file_path in results.items():
        click.echo(f"  {click.style('✓', fg='green')} {file_path}")

    # Report skipped files
    skipped = generator.skipped_files
    if skipped:
        click.echo()
        click.secho("Skipped (files have project-specific content):", fg="yellow")
        for format_name, path_or_msg in skipped.items():
            click.echo(f"  {click.style('○', fg='yellow')} {path_or_msg}")
        click.echo()
        click.echo("Use --force to overwrite these files.")

    if results:
        click.echo()
        click.secho("Done! Generated files are ready.", fg="green")
    elif skipped:
        click.echo()
        click.secho("No files generated (all skipped).", fg="yellow")

    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Review the generated files")
    click.echo("  2. Customize agent_instructions/ for your project")
    click.echo("  3. Re-run this command after changes to sync files")


@main.group()
def cache() -> None:
    """Manage the API response cache."""
    pass


@cache.command("clear")
@click.option("--key", "-k", help="Clear specific cache key")
def cache_clear(key: str | None) -> None:
    """Clear cached API responses."""
    from lib.vibe.utils.cache import get_cache

    c = get_cache()
    count = c.invalidate(key)
    click.echo(f"Cleared {count} cache entries.")


@cache.command("status")
def cache_status() -> None:
    """Show cache status."""
    from lib.vibe.utils.cache import get_cache

    c = get_cache()
    entries = c.status()
    if not entries:
        click.echo("Cache is empty.")
        return
    click.echo(f"\nCached entries ({len(entries)}):")
    for entry in entries:
        if "error" in entry:
            click.echo(f"  {entry['key']}: {entry['error']}")
        else:
            age = entry["age_seconds"]
            remaining = entry["remaining_seconds"]
            status = "expired" if entry["expired"] else f"{remaining}s remaining"
            click.echo(f"  {entry['key']}: cached {age}s ago ({status})")


# Register figma command group
main.add_command(figma)


if __name__ == "__main__":
    main()
