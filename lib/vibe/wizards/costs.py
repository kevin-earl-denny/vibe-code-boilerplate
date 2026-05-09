"""Cost tracking setup wizard."""

from typing import Any

import click

from lib.vibe.costs.registry import PROVIDER_REGISTRY
from lib.vibe.tools import require_interactive
from lib.vibe.ui.components import MultiSelect

# Map provider names to display names and env var hints
PROVIDER_INFO: dict[str, tuple[str, str]] = {
    "vercel": ("Vercel", "VERCEL_TOKEN"),
    "neon": ("Neon", "NEON_API_KEY"),
    "supabase": ("Supabase", "SUPABASE_ACCESS_TOKEN"),
    "fly": ("Fly.io", "FLY_API_TOKEN"),
    "github": ("GitHub Actions", "GITHUB_TOKEN (or gh CLI)"),
    "openai": ("OpenAI", "OPENAI_API_KEY"),
    "anthropic": ("Anthropic", "ANTHROPIC_API_KEY"),
    "sentry": ("Sentry", "SENTRY_AUTH_TOKEN"),
}


def run_costs_wizard(config: dict[str, Any]) -> bool:
    """Configure cost tracking integration.

    Args:
        config: Configuration dict to update.

    Returns:
        True if configuration was successful.
    """
    ok, error = require_interactive("Cost Tracking")
    if not ok:
        click.echo(f"\n{error}")
        return False

    click.echo("\n--- Cost Tracking Setup ---")
    click.echo()
    click.echo("Track spending across your cloud services.")
    click.echo("API keys are read from environment variables (.env.local).")
    click.echo()

    # Initialize cost_tracking section
    if "cost_tracking" not in config:
        config["cost_tracking"] = {}

    ct = config["cost_tracking"]
    ct["enabled"] = True

    if "providers" not in ct:
        ct["providers"] = {}

    # Auto-detect which providers might be relevant
    options: list[tuple[str, str, bool]] = []
    for name in PROVIDER_REGISTRY:
        display_name, env_var = PROVIDER_INFO.get(name, (name.title(), ""))
        default_on = _should_default_enable(name, config)
        desc = f"Env: {env_var}" if env_var else ""
        options.append((display_name, desc, default_on))

    provider_names = list(PROVIDER_REGISTRY.keys())

    multi = MultiSelect(
        title="Select providers to track:",
        options=options,
    )
    selected_indices = multi.show()

    # Update provider config
    for i, name in enumerate(provider_names):
        idx = i + 1  # 1-based
        if idx in selected_indices:
            if name not in ct["providers"] or not isinstance(ct["providers"].get(name), dict):
                ct["providers"][name] = {}
            ct["providers"][name]["enabled"] = True
        else:
            if name in ct["providers"] and isinstance(ct["providers"][name], dict):
                ct["providers"][name]["enabled"] = False

    # Budget
    click.echo()
    budget = click.prompt(
        "Monthly budget (USD, 0 to skip)",
        type=float,
        default=ct.get("budget_monthly", 0.0),
    )
    ct["budget_monthly"] = budget

    if budget > 0:
        threshold = click.prompt(
            "Alert threshold (% of budget)",
            type=int,
            default=int(ct.get("alert_threshold_pct", 80)),
        )
        ct["alert_threshold_pct"] = threshold

    # Manual entries
    click.echo()
    if click.confirm("Add manual fixed-cost entries (Figma, domains, etc.)?", default=False):
        manual = ct.get("manual", []) if "manual" not in ct.get("providers", {}) else []
        if "providers" in ct and "manual" in ct["providers"]:
            manual = ct["providers"]["manual"]

        _add_manual_entries(manual)
        ct["providers"]["manual"] = manual

    click.echo()
    click.echo("Cost tracking configured!")
    click.echo()

    enabled = [
        PROVIDER_INFO.get(n, (n.title(), ""))[0]
        for n in provider_names
        if ct["providers"].get(n, {}).get("enabled", False)
    ]
    if enabled:
        click.echo(f"Enabled providers: {', '.join(enabled)}")
    if budget > 0:
        click.echo(f"Monthly budget: ${budget:,.2f}")
    click.echo()
    click.echo("Add API keys to .env.local, then run: bin/vibe costs")

    return True


def _should_default_enable(provider_name: str, config: dict[str, Any]) -> bool:
    """Guess whether a provider should be enabled by default based on existing config."""
    # Check if provider is already enabled in cost_tracking
    ct = config.get("cost_tracking", {}).get("providers", {})
    if isinstance(ct.get(provider_name), dict):
        return bool(ct[provider_name].get("enabled", False))

    # Check if the corresponding deployment/integration is configured
    deployment = config.get("deployment", {})
    if provider_name == "vercel" and deployment.get("vercel", {}).get("enabled"):
        return True
    if provider_name == "fly" and deployment.get("fly", {}).get("enabled"):
        return True

    database = config.get("database", {})
    if provider_name == "neon" and database.get("neon", {}).get("enabled"):
        return True
    if provider_name == "supabase" and database.get("supabase", {}).get("enabled"):
        return True

    return False


def _add_manual_entries(manual: list) -> None:
    """Interactively add manual cost entries."""
    while True:
        name = click.prompt("Entry name (or 'done' to finish)", default="done")
        if name.lower() == "done":
            break
        cost = click.prompt(f"  {name} cost (USD)", type=float)
        billing = click.prompt(
            f"  {name} billing cycle",
            type=click.Choice(["monthly", "yearly"]),
            default="monthly",
        )
        manual.append({"name": name, "cost": cost, "billing": billing})
        click.echo(f"  Added: {name} ${cost:.2f}/{billing}")
        click.echo()
