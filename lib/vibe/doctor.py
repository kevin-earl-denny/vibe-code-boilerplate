"""Doctor: Validate project configuration and health."""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from lib.vibe.config import config_exists, load_config
from lib.vibe.secrets.allowlist import validate_allowlist
from lib.vibe.state import set_last_doctor_run
from lib.vibe.wizards.github import check_gh_cli_auth


class Status(Enum):
    """Check status."""

    PASS = "✓"
    WARN = "⚠"
    FAIL = "✗"
    SKIP = "○"


@dataclass
class CheckResult:
    """Result of a health check."""

    name: str
    status: Status
    message: str
    fix_hint: str | None = None
    category: str = "general"


def run_doctor(
    verbose: bool = False,
    check_github_actions: bool = False,
    live_checks: bool = False,
) -> list[CheckResult]:
    """
    Run all health checks.

    Args:
        verbose: Show additional details
        check_github_actions: Also check GitHub Actions secrets/workflows
        live_checks: Run live integration checks (API calls to verify connections)

    Returns:
        List of check results
    """
    results = []

    # Core checks
    results.append(check_config_exists())
    results.append(check_gitignore())
    results.append(check_python_version())

    # Tool checks
    results.append(check_git())
    results.append(check_gh_cli())

    # Config-dependent checks
    if config_exists():
        config = load_config()
        results.append(check_config_schema())
        results.append(check_tracker_config(config))
        results.append(check_label_sync(config))
        results.append(check_github_config(config))
        results.append(check_secrets_allowlist())

        # Integration checks
        results.extend(check_integrations(config, verbose))

        # Infrastructure readiness (helpful guidance)
        results.extend(check_infrastructure_readiness(config))

        # Cost tracking check
        results.append(check_cost_tracking(config))

        # Integration freshness check
        results.append(check_integration_freshness())

        # Live integration checks (actual API calls)
        if live_checks:
            results.extend(run_live_validation_checks(config))

    # direnv check
    results.append(check_direnv())

    # Local hooks check
    results.append(check_local_hooks())

    # Git hooks check (.githooks/ + core.hooksPath)
    results.append(check_git_hooks_path())

    # Worktree check
    results.append(check_stale_worktrees())

    # GitHub Actions checks (optional, requires gh CLI)
    if check_github_actions:
        results.extend(check_github_actions_setup())

    # Update last run time
    set_last_doctor_run()

    return results


def run_live_validation_checks(config: dict) -> list[CheckResult]:
    """
    Run live integration validation checks.

    These checks make actual API calls to verify integrations are working.
    """
    from lib.vibe.ui.validation import SetupValidator

    results = []
    validator = SetupValidator(config)
    validation_results = validator.run_all()

    for vr in validation_results:
        status = Status.PASS if vr.success else Status.FAIL
        results.append(
            CheckResult(
                name=f"Live: {vr.name}",
                status=status,
                message=vr.message,
                fix_hint=vr.details if not vr.success else None,
                category="live_validation",
            )
        )

    return results


def check_config_exists() -> CheckResult:
    """Check if .vibe/config.json exists."""
    if config_exists():
        return CheckResult(
            name="Config file",
            status=Status.PASS,
            message=".vibe/config.json exists",
        )
    return CheckResult(
        name="Config file",
        status=Status.FAIL,
        message=".vibe/config.json not found",
        fix_hint="Run 'bin/vibe setup' to create configuration",
    )


def check_config_schema() -> CheckResult:
    """Validate config schema."""
    from lib.vibe.config_schema import validate_config

    config = load_config()
    errors = validate_config(config)

    if not errors:
        return CheckResult(
            name="Config schema",
            status=Status.PASS,
            message="Configuration is valid",
        )

    return CheckResult(
        name="Config schema",
        status=Status.WARN,
        message=f"{len(errors)} issue(s): {errors[0]}",
        fix_hint="Review .vibe/config.json for typos or missing fields",
    )


def check_gitignore() -> CheckResult:
    """Check if .gitignore has required entries."""
    gitignore = Path(".gitignore")
    if not gitignore.exists():
        return CheckResult(
            name="Gitignore",
            status=Status.FAIL,
            message=".gitignore not found",
            fix_hint="Create .gitignore with required entries",
        )

    content = gitignore.read_text()
    required = [".vibe/local_state.json", ".env.local", ".env"]

    missing = [entry for entry in required if entry not in content]

    if missing:
        return CheckResult(
            name="Gitignore",
            status=Status.WARN,
            message=f"Missing entries: {', '.join(missing)}",
            fix_hint="Add missing entries to .gitignore",
        )

    return CheckResult(
        name="Gitignore",
        status=Status.PASS,
        message="All required entries present",
    )


def check_python_version() -> CheckResult:
    """Check Python version is 3.11+."""
    import sys

    version = sys.version_info
    if version >= (3, 11):
        return CheckResult(
            name="Python version",
            status=Status.PASS,
            message=f"Python {version.major}.{version.minor}",
        )

    return CheckResult(
        name="Python version",
        status=Status.FAIL,
        message=f"Python {version.major}.{version.minor} (need 3.11+)",
        fix_hint="Install Python 3.11 or later",
    )


def check_git() -> CheckResult:
    """Check git is installed and we're in a repo."""
    if not shutil.which("git"):
        return CheckResult(
            name="Git",
            status=Status.FAIL,
            message="git not found",
            fix_hint="Install git",
        )

    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return CheckResult(
            name="Git",
            status=Status.FAIL,
            message="Not a git repository",
            fix_hint="Run 'git init' or clone a repository",
        )

    return CheckResult(
        name="Git",
        status=Status.PASS,
        message="Git repository detected",
    )


def check_gh_cli() -> CheckResult:
    """Check GitHub CLI is installed and authenticated."""
    if not shutil.which("gh"):
        return CheckResult(
            name="GitHub CLI",
            status=Status.WARN,
            message="gh CLI not installed",
            fix_hint="Install from https://cli.github.com/",
        )

    if check_gh_cli_auth():
        return CheckResult(
            name="GitHub CLI",
            status=Status.PASS,
            message="gh CLI authenticated",
        )

    return CheckResult(
        name="GitHub CLI",
        status=Status.WARN,
        message="gh CLI not authenticated",
        fix_hint="Run 'gh auth login'",
    )


def check_tracker_config(config: dict) -> CheckResult:
    """Check tracker configuration."""
    tracker_type = config.get("tracker", {}).get("type")

    if not tracker_type:
        return CheckResult(
            name="Tracker",
            status=Status.SKIP,
            message="No tracker configured (optional)",
            fix_hint="Run 'bin/vibe setup --wizard tracker' to configure",
            category="integration",
        )

    if tracker_type == "shortcut":
        if os.environ.get("SHORTCUT_API_TOKEN"):
            return CheckResult(
                name="Tracker",
                status=Status.PASS,
                message="Shortcut configured with API token",
                category="integration",
            )
        return CheckResult(
            name="Tracker",
            status=Status.WARN,
            message="Shortcut configured but SHORTCUT_API_TOKEN not set",
            fix_hint="Add SHORTCUT_API_TOKEN to .env.local",
            category="integration",
        )

    if tracker_type == "linear":
        if os.environ.get("LINEAR_API_KEY"):
            return CheckResult(
                name="Tracker",
                status=Status.PASS,
                message="Linear configured with API key",
                category="integration",
            )
        return CheckResult(
            name="Tracker",
            status=Status.WARN,
            message="Linear configured but LINEAR_API_KEY not set",
            fix_hint="Add LINEAR_API_KEY to .env.local",
            category="integration",
        )

    return CheckResult(
        name="Tracker",
        status=Status.WARN,
        message=f"Unknown tracker type: {tracker_type}",
        category="integration",
    )


def check_label_sync(config: dict) -> CheckResult:
    """Check whether config labels look like unsynced defaults."""
    from lib.vibe.config import DEFAULT_CONFIG

    tracker_type = config.get("tracker", {}).get("type")
    if not tracker_type:
        return CheckResult(
            name="Label sync",
            status=Status.SKIP,
            message="No tracker configured",
            category="integration",
        )

    current_labels = config.get("labels", {})
    default_labels = DEFAULT_CONFIG.get("labels", {})

    # If area labels are exactly the defaults, they likely haven't been synced
    if current_labels.get("area") == default_labels.get("area"):
        return CheckResult(
            name="Label sync",
            status=Status.WARN,
            message="Labels appear to be defaults (not synced from tracker)",
            fix_hint="Run 'bin/vibe sync-labels' to fetch labels from your tracker",
            category="integration",
        )

    return CheckResult(
        name="Label sync",
        status=Status.PASS,
        message="Area labels differ from defaults (likely synced or customized)",
        category="integration",
    )


def check_github_config(config: dict) -> CheckResult:
    """Check GitHub configuration."""
    github = config.get("github", {})
    auth_method = github.get("auth_method")
    owner = github.get("owner")
    repo = github.get("repo")

    if not auth_method:
        return CheckResult(
            name="GitHub config",
            status=Status.FAIL,
            message="GitHub not configured",
            fix_hint="Run 'bin/vibe setup' to configure GitHub",
        )

    if not owner or not repo:
        return CheckResult(
            name="GitHub config",
            status=Status.WARN,
            message="GitHub owner/repo not set",
            fix_hint="Set github.owner and github.repo in .vibe/config.json",
        )

    return CheckResult(
        name="GitHub config",
        status=Status.PASS,
        message=f"GitHub: {owner}/{repo} ({auth_method})",
    )


def check_secrets_allowlist() -> CheckResult:
    """Check secrets allowlist is valid."""
    valid, issues = validate_allowlist()

    if valid:
        return CheckResult(
            name="Secrets allowlist",
            status=Status.PASS,
            message="Allowlist is valid",
        )

    return CheckResult(
        name="Secrets allowlist",
        status=Status.WARN,
        message=f"Allowlist issues: {', '.join(issues)}",
        fix_hint="Fix issues in .vibe/secrets.allowlist.json",
    )


def check_direnv() -> CheckResult:
    """Check direnv configuration for automatic env variable loading."""
    from lib.vibe.env import check_direnv_status

    status = check_direnv_status()

    if not status["envrc_exists"]:
        return CheckResult(
            name="direnv",
            status=Status.SKIP,
            message=".envrc not configured (optional)",
            fix_hint="Run 'bin/vibe setup' to create .envrc for automatic env loading",
        )

    if not status["direnv_installed"]:
        return CheckResult(
            name="direnv",
            status=Status.WARN,
            message=".envrc exists but direnv is not installed",
            fix_hint="Install direnv: https://direnv.net/docs/installation.html",
        )

    if status["direnv_allowed"] is False:
        return CheckResult(
            name="direnv",
            status=Status.WARN,
            message=".envrc exists but not allowed",
            fix_hint="Run 'direnv allow' in the project root",
        )

    if status["direnv_allowed"] is True:
        return CheckResult(
            name="direnv",
            status=Status.PASS,
            message="direnv configured and allowed",
        )

    # Could not determine allow status
    return CheckResult(
        name="direnv",
        status=Status.PASS,
        message="direnv installed, .envrc exists",
    )


def check_local_hooks() -> CheckResult:
    """Check if local Claude Code hooks are configured."""
    hooks_file = Path(".claude/settings.local.json")

    if not hooks_file.exists():
        return CheckResult(
            name="Local hooks",
            status=Status.SKIP,
            message="Not configured (optional)",
            fix_hint="Copy .claude/settings.local.json.example to enable",
            category="integration",
        )

    try:
        content = json.loads(hooks_file.read_text())
        hooks = content.get("hooks", {})
        if hooks:
            return CheckResult(
                name="Local hooks",
                status=Status.PASS,
                message=f"{len(hooks)} hook(s) configured",
                category="integration",
            )
        return CheckResult(
            name="Local hooks",
            status=Status.WARN,
            message="File exists but no hooks defined",
            category="integration",
        )
    except (json.JSONDecodeError, OSError) as e:
        return CheckResult(
            name="Local hooks",
            status=Status.WARN,
            message=f"Invalid JSON: {e}",
            fix_hint="Fix JSON syntax in .claude/settings.local.json",
            category="integration",
        )


def check_git_hooks_path() -> CheckResult:
    """Check that the project's git hooks are wired up.

    The boilerplate ships a .githooks/ directory with pre-commit + pre-push
    hooks. They only fire when core.hooksPath is set to .githooks (a one-time
    per-clone setup). This check warns if the path isn't set or points
    elsewhere.
    """
    githooks_dir = Path(".githooks")
    if not githooks_dir.is_dir():
        # No .githooks/ in this project — nothing to wire up.
        return CheckResult(
            name="Git hooks",
            status=Status.SKIP,
            message="No .githooks/ directory in project",
            category="integration",
        )

    try:
        result = subprocess.run(
            ["git", "config", "--local", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        return CheckResult(
            name="Git hooks",
            status=Status.WARN,
            message=f"Could not query git config: {exc}",
            category="integration",
        )

    configured = result.stdout.strip()
    expected = ".githooks"

    if not configured:
        return CheckResult(
            name="Git hooks",
            status=Status.WARN,
            message="core.hooksPath not configured — pre-commit/pre-push hooks won't fire",
            fix_hint="Run: git config --local core.hooksPath .githooks",
            category="integration",
        )

    if configured != expected:
        return CheckResult(
            name="Git hooks",
            status=Status.WARN,
            message=f"core.hooksPath is '{configured}', expected '{expected}'",
            fix_hint=f"Run: git config --local core.hooksPath {expected}",
            category="integration",
        )

    # Verify the hook files are executable. Non-executable hooks are silently
    # ignored by git, which is a common cause of "hooks aren't running" reports.
    non_executable = []
    for hook_name in ("pre-commit", "pre-push"):
        hook_path = githooks_dir / hook_name
        if hook_path.exists() and not os.access(hook_path, os.X_OK):
            non_executable.append(hook_name)

    if non_executable:
        return CheckResult(
            name="Git hooks",
            status=Status.WARN,
            message=f"Hooks not executable: {', '.join(non_executable)}",
            fix_hint=f"Run: chmod +x .githooks/{' .githooks/'.join(non_executable)}",
            category="integration",
        )

    return CheckResult(
        name="Git hooks",
        status=Status.PASS,
        message="core.hooksPath = .githooks (pre-commit, pre-push wired up)",
        category="integration",
    )


def check_stale_worktrees() -> CheckResult:
    """Check for stale worktrees."""
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return CheckResult(
                name="Worktrees",
                status=Status.SKIP,
                message="Could not list worktrees",
            )

        # Count worktrees (excluding main)
        worktrees = [
            line
            for line in result.stdout.split("\n")
            if line.startswith("worktree ") and not line.endswith(str(Path.cwd()))
        ]

        if len(worktrees) == 0:
            return CheckResult(
                name="Worktrees",
                status=Status.PASS,
                message="No active worktrees",
            )

        return CheckResult(
            name="Worktrees",
            status=Status.PASS,
            message=f"{len(worktrees)} active worktree(s)",
        )

    except (subprocess.CalledProcessError, OSError):
        return CheckResult(
            name="Worktrees",
            status=Status.SKIP,
            message="Could not check worktrees",
        )


def check_integrations(config: dict, verbose: bool = False) -> list[CheckResult]:
    """Check optional integrations."""
    results = []

    # PromptVault
    if os.environ.get("PROMPTVAULT_API_KEY"):
        results.append(
            CheckResult(
                name="PromptVault",
                status=Status.PASS,
                message="API key configured",
                category="integration",
            )
        )
    else:
        results.append(
            CheckResult(
                name="PromptVault",
                status=Status.SKIP,
                message="Not configured (optional)",
                fix_hint="Add PROMPTVAULT_API_KEY to .env.local for LLM apps",
                category="integration",
            )
        )

    # Fly.io
    if shutil.which("fly") or shutil.which("flyctl"):
        try:
            result = subprocess.run(
                ["fly", "auth", "whoami"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                results.append(
                    CheckResult(
                        name="Fly.io",
                        status=Status.PASS,
                        message="CLI authenticated",
                        category="integration",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        name="Fly.io",
                        status=Status.WARN,
                        message="CLI installed but not authenticated",
                        fix_hint="Run 'fly auth login'",
                        category="integration",
                    )
                )
        except (subprocess.CalledProcessError, OSError):
            results.append(
                CheckResult(
                    name="Fly.io",
                    status=Status.SKIP,
                    message="CLI check failed",
                    category="integration",
                )
            )
    else:
        results.append(
            CheckResult(
                name="Fly.io",
                status=Status.SKIP,
                message="CLI not installed (optional)",
                category="integration",
            )
        )

    # Vercel
    if shutil.which("vercel"):
        try:
            result = subprocess.run(
                ["vercel", "whoami"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                results.append(
                    CheckResult(
                        name="Vercel",
                        status=Status.PASS,
                        message="CLI authenticated",
                        category="integration",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        name="Vercel",
                        status=Status.WARN,
                        message="CLI installed but not authenticated",
                        fix_hint="Run 'vercel login'",
                        category="integration",
                    )
                )
        except (subprocess.CalledProcessError, OSError):
            results.append(
                CheckResult(
                    name="Vercel",
                    status=Status.SKIP,
                    message="CLI check failed",
                    category="integration",
                )
            )
    else:
        results.append(
            CheckResult(
                name="Vercel",
                status=Status.SKIP,
                message="CLI not installed (optional)",
                category="integration",
            )
        )

    # Supabase
    if shutil.which("supabase"):
        results.append(
            CheckResult(
                name="Supabase",
                status=Status.PASS,
                message="CLI installed",
                category="integration",
            )
        )
    elif os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"):
        results.append(
            CheckResult(
                name="Supabase",
                status=Status.PASS,
                message="Environment variables configured",
                category="integration",
            )
        )
    else:
        results.append(
            CheckResult(
                name="Supabase",
                status=Status.SKIP,
                message="Not configured (optional)",
                category="integration",
            )
        )

    # Sentry
    if os.environ.get("SENTRY_DSN"):
        results.append(
            CheckResult(
                name="Sentry",
                status=Status.PASS,
                message="DSN configured",
                category="integration",
            )
        )
    else:
        results.append(
            CheckResult(
                name="Sentry",
                status=Status.SKIP,
                message="Not configured (optional)",
                fix_hint="Add SENTRY_DSN to .env.local for error monitoring",
                category="integration",
            )
        )

    # Neon
    if os.environ.get("NEON_API_KEY") or os.environ.get("DATABASE_URL", "").startswith("postgres"):
        if os.environ.get("NEON_API_KEY"):
            results.append(
                CheckResult(
                    name="Neon",
                    status=Status.PASS,
                    message="API key configured",
                    category="integration",
                )
            )
        else:
            results.append(
                CheckResult(
                    name="Neon",
                    status=Status.PASS,
                    message="DATABASE_URL configured",
                    category="integration",
                )
            )
    elif shutil.which("neonctl"):
        results.append(
            CheckResult(
                name="Neon",
                status=Status.WARN,
                message="CLI installed but not configured",
                fix_hint="Add NEON_API_KEY or DATABASE_URL to .env.local",
                category="integration",
            )
        )
    else:
        results.append(
            CheckResult(
                name="Neon",
                status=Status.SKIP,
                message="Not configured (optional)",
                fix_hint="Add NEON_API_KEY for serverless Postgres",
                category="integration",
            )
        )

    # Playwright E2E testing
    playwright_config = None
    for config_name in ["playwright.config.ts", "playwright.config.js", "playwright.config.mjs"]:
        if Path(config_name).exists():
            playwright_config = config_name
            break

    if playwright_config:
        # Check if node_modules/@playwright/test exists
        if Path("node_modules/@playwright/test").exists():
            results.append(
                CheckResult(
                    name="Playwright",
                    status=Status.PASS,
                    message=f"Configured ({playwright_config})",
                    category="integration",
                )
            )
        else:
            results.append(
                CheckResult(
                    name="Playwright",
                    status=Status.WARN,
                    message="Config exists but packages not installed",
                    fix_hint="Run 'npm install' to install Playwright",
                    category="integration",
                )
            )
    else:
        results.append(
            CheckResult(
                name="Playwright",
                status=Status.SKIP,
                message="Not configured (optional)",
                fix_hint="Run 'bin/vibe setup -w playwright' for E2E testing",
                category="integration",
            )
        )

    return results


def check_infrastructure_readiness(config: dict) -> list[CheckResult]:
    """
    Check infrastructure configuration (database, hosting, monitoring).

    Shows helpful guidance for early infrastructure setup.
    """
    results = []

    # Database check
    database = config.get("database", {})
    db_provider = database.get("provider")
    has_neon = database.get("neon", {}).get("enabled")
    has_supabase = database.get("supabase", {}).get("enabled")

    if db_provider or has_neon or has_supabase:
        provider_name = db_provider or ("Neon" if has_neon else "Supabase")
        results.append(
            CheckResult(
                name="Database",
                status=Status.PASS,
                message=f"{provider_name.title()} configured",
                category="infrastructure",
            )
        )
    else:
        results.append(
            CheckResult(
                name="Database",
                status=Status.SKIP,
                message="Not configured",
                fix_hint="Run 'bin/vibe setup -w database' to set up Neon or Supabase",
                category="infrastructure",
            )
        )

    # Hosting check
    has_vercel = config.get("deployment", {}).get("vercel", {}).get("enabled")
    has_fly = config.get("deployment", {}).get("fly", {}).get("enabled")

    if has_vercel or has_fly:
        provider = "Vercel" if has_vercel else "Fly.io"
        results.append(
            CheckResult(
                name="Hosting",
                status=Status.PASS,
                message=f"{provider} configured",
                category="infrastructure",
            )
        )
    else:
        results.append(
            CheckResult(
                name="Hosting",
                status=Status.SKIP,
                message="Not configured",
                fix_hint="Run 'bin/vibe setup -w vercel' or '-w fly' when ready to deploy",
                category="infrastructure",
            )
        )

    # Monitoring check
    has_sentry = os.environ.get("SENTRY_DSN")

    if has_sentry:
        results.append(
            CheckResult(
                name="Monitoring",
                status=Status.PASS,
                message="Sentry configured",
                category="infrastructure",
            )
        )
    else:
        results.append(
            CheckResult(
                name="Monitoring",
                status=Status.SKIP,
                message="Not configured",
                fix_hint="Add SENTRY_DSN to .env.local for error tracking",
                category="infrastructure",
            )
        )

    return results


def check_cost_tracking(config: dict) -> CheckResult:
    """Check cost tracking configuration."""
    ct = config.get("cost_tracking", {})

    if not ct.get("enabled"):
        return CheckResult(
            name="Cost tracking",
            status=Status.SKIP,
            message="Not enabled (optional)",
            fix_hint="Run 'bin/vibe setup --wizard cost-tracking' to configure",
            category="integration",
        )

    providers = ct.get("providers", {})
    enabled = [
        name
        for name, cfg in providers.items()
        if name != "manual" and isinstance(cfg, dict) and cfg.get("enabled")
    ]

    if not enabled:
        return CheckResult(
            name="Cost tracking",
            status=Status.WARN,
            message="Enabled but no providers configured",
            fix_hint="Run 'bin/vibe setup --wizard cost-tracking' to add providers",
            category="integration",
        )

    budget = ct.get("budget_monthly", 0)
    if not budget:
        return CheckResult(
            name="Cost tracking",
            status=Status.WARN,
            message=f"{len(enabled)} provider(s) configured, no budget set",
            fix_hint="Set budget_monthly in .vibe/config.json cost_tracking section",
            category="integration",
        )

    return CheckResult(
        name="Cost tracking",
        status=Status.PASS,
        message=f"{len(enabled)} provider(s), budget ${budget:,.0f}/mo",
        category="integration",
    )


def check_integration_freshness() -> CheckResult:
    """Check if any integrations are stale (> 30 days since verification)."""
    freshness_file = Path(".vibe/integration-freshness.json")

    if not freshness_file.exists():
        return CheckResult(
            name="Integration freshness",
            status=Status.SKIP,
            message="No freshness tracking file",
            fix_hint="See recipes/workflows/integration-freshness.md",
            category="integration",
        )

    try:
        data = json.loads(freshness_file.read_text())
        integrations = data.get("integrations", {})

        if not integrations:
            return CheckResult(
                name="Integration freshness",
                status=Status.SKIP,
                message="No integrations tracked",
                category="integration",
            )

        today = datetime.now()
        stale_days = 30
        stale_integrations = []

        for name, info in integrations.items():
            last_checked = info.get("last_checked")
            if not last_checked:
                stale_integrations.append(f"{name} (never)")
                continue

            try:
                checked_date = datetime.strptime(last_checked, "%Y-%m-%d")
                days_ago = (today - checked_date).days
                if days_ago > stale_days:
                    stale_integrations.append(f"{name} ({days_ago}d)")
            except ValueError:
                stale_integrations.append(f"{name} (invalid date)")

        if stale_integrations:
            return CheckResult(
                name="Integration freshness",
                status=Status.WARN,
                message=f"Stale: {', '.join(stale_integrations)}",
                fix_hint="Re-verify integrations and update .vibe/integration-freshness.json",
                category="integration",
            )

        return CheckResult(
            name="Integration freshness",
            status=Status.PASS,
            message=f"All {len(integrations)} integrations verified within {stale_days}d",
            category="integration",
        )

    except json.JSONDecodeError as e:
        return CheckResult(
            name="Integration freshness",
            status=Status.WARN,
            message=f"Invalid JSON: {e}",
            fix_hint="Fix .vibe/integration-freshness.json syntax",
            category="integration",
        )
    except OSError as e:
        return CheckResult(
            name="Integration freshness",
            status=Status.WARN,
            message=f"Error checking: {e}",
            category="integration",
        )


def check_github_actions_setup() -> list[CheckResult]:
    """Check GitHub Actions secrets and workflow status."""
    results = []

    if not shutil.which("gh"):
        results.append(
            CheckResult(
                name="GitHub Actions",
                status=Status.SKIP,
                message="gh CLI required for this check",
                category="github_actions",
            )
        )
        return results

    # Check for required secrets
    try:
        result = subprocess.run(
            ["gh", "secret", "list"],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            secrets = result.stdout.strip().split("\n") if result.stdout.strip() else []
            secret_names = [s.split()[0] for s in secrets if s]

            # Check for LINEAR_API_KEY
            if "LINEAR_API_KEY" in secret_names:
                results.append(
                    CheckResult(
                        name="GH Secret: LINEAR_API_KEY",
                        status=Status.PASS,
                        message="Secret exists",
                        category="github_actions",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        name="GH Secret: LINEAR_API_KEY",
                        status=Status.WARN,
                        message="Not set (needed for workflow status updates)",
                        fix_hint="Add via: gh secret set LINEAR_API_KEY",
                        category="github_actions",
                    )
                )

        else:
            results.append(
                CheckResult(
                    name="GitHub Secrets",
                    status=Status.WARN,
                    message="Could not list secrets (check permissions)",
                    category="github_actions",
                )
            )

    except (subprocess.CalledProcessError, OSError) as e:
        results.append(
            CheckResult(
                name="GitHub Secrets",
                status=Status.WARN,
                message=f"Error checking secrets: {e}",
                category="github_actions",
            )
        )

    # Check recent workflow runs
    try:
        result = subprocess.run(
            ["gh", "run", "list", "--limit", "5", "--json", "name,status,conclusion"],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0 and result.stdout.strip():
            runs = json.loads(result.stdout)
            failed = [r for r in runs if r.get("conclusion") == "failure"]

            if failed:
                results.append(
                    CheckResult(
                        name="Recent workflows",
                        status=Status.WARN,
                        message=f"{len(failed)}/{len(runs)} recent runs failed",
                        fix_hint="Check: gh run list --limit 5",
                        category="github_actions",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        name="Recent workflows",
                        status=Status.PASS,
                        message="All recent runs passed",
                        category="github_actions",
                    )
                )
        else:
            results.append(
                CheckResult(
                    name="Recent workflows",
                    status=Status.SKIP,
                    message="No recent workflow runs",
                    category="github_actions",
                )
            )

    except (subprocess.CalledProcessError, OSError, json.JSONDecodeError):
        results.append(
            CheckResult(
                name="Recent workflows",
                status=Status.SKIP,
                message="Could not check workflow runs",
                category="github_actions",
            )
        )

    return results


def print_results(results: list[CheckResult], show_skipped: bool = True) -> int:
    """
    Print check results and return exit code.

    Returns:
        0 if all pass, 1 if any failures
    """
    print("\n" + "=" * 50)
    print("  Vibe Doctor - Health Check")
    print("=" * 50 + "\n")

    has_failure = False

    # Group by category
    categories: dict[str, list[CheckResult]] = {}
    for result in results:
        cat = result.category
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(result)

    # Print general first, then infrastructure, integrations, live validation, then github_actions
    category_order = [
        "general",
        "infrastructure",
        "integration",
        "live_validation",
        "github_actions",
    ]
    category_names = {
        "general": "Core Checks",
        "infrastructure": "Infrastructure (configure early for smooth deploys)",
        "integration": "Integrations",
        "live_validation": "Live Integration Checks",
        "github_actions": "GitHub Actions",
    }

    for cat in category_order:
        if cat not in categories:
            continue

        cat_results = categories[cat]

        # Skip category if all are SKIP and not showing skipped
        if not show_skipped and all(r.status == Status.SKIP for r in cat_results):
            continue

        print(f"  {category_names.get(cat, cat)}")
        print("  " + "-" * 30)

        for result in cat_results:
            if not show_skipped and result.status == Status.SKIP:
                continue

            status_char = result.status.value
            print(f"  {status_char} {result.name}: {result.message}")

            if result.fix_hint and result.status in (Status.FAIL, Status.WARN):
                print(f"      → {result.fix_hint}")

            if result.status == Status.FAIL:
                has_failure = True

        print()

    passed = sum(1 for r in results if r.status == Status.PASS)
    warned = sum(1 for r in results if r.status == Status.WARN)
    skipped = sum(1 for r in results if r.status == Status.SKIP)
    total = len(results)

    summary = f"  {passed}/{total} passed"
    if warned:
        summary += f", {warned} warnings"
    if skipped:
        summary += f", {skipped} skipped"
    print(summary)
    print()

    return 1 if has_failure else 0


if __name__ == "__main__":
    import sys

    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    check_actions = "--github-actions" in sys.argv or "-g" in sys.argv
    live = "--live" in sys.argv or "-l" in sys.argv

    results = run_doctor(verbose=verbose, check_github_actions=check_actions, live_checks=live)
    sys.exit(print_results(results))
