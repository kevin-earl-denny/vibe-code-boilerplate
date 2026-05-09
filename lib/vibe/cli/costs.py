"""Cost tracking CLI commands."""

from datetime import datetime

import click

from lib.vibe.costs.base import CostReport, ManualCostEntry
from lib.vibe.costs.registry import (
    get_all_providers,
    get_budget_config,
    get_cached_report,
    get_cost_tracking_config,
    get_manual_entries,
    is_cost_tracking_enabled,
    load_provider,
    save_cached_report,
)
from lib.vibe.ui.components import Spinner


def _current_month() -> str:
    """Return current month as YYYY-MM."""
    return datetime.now().strftime("%Y-%m")


def _month_display(month: str) -> str:
    """Return human-readable month (e.g., 'February 2026')."""
    try:
        dt = datetime.strptime(month, "%Y-%m")
        return dt.strftime("%B %Y")
    except ValueError:
        return month


def _color_for_pct(pct: float) -> str:
    """Return color name based on budget usage percentage."""
    if pct >= 95:
        return "red"
    if pct >= 80:
        return "yellow"
    return "green"


def _format_cost(amount: float) -> str:
    """Format a dollar amount."""
    return f"${amount:,.2f}"


def _fetch_provider_report(provider_name: str, month: str, config: dict) -> CostReport | None:
    """Fetch a cost report for a provider, using cache when available."""
    # Check cache first
    cached = get_cached_report(provider_name, month)
    if cached is not None:
        return cached

    providers_config = config.get("providers", {})
    provider_cfg = providers_config.get(provider_name, {})
    provider = load_provider(
        provider_name, provider_cfg if isinstance(provider_cfg, dict) else None
    )
    if provider is None:
        return None

    if not provider.check_credentials():
        return CostReport(
            provider=provider.display_name,
            total=0.0,
            is_estimated=True,
        )

    try:
        report = provider.get_current_costs(month)
        save_cached_report(report, month)
        return report
    except Exception:  # noqa: BLE001
        return None


@click.group()
def main() -> None:
    """Track costs across cloud services."""


@main.command("summary")
@click.option("--month", "-m", default=None, help="Month to report (YYYY-MM). Defaults to current.")
@click.option("--provider", "-p", default=None, help="Show only a single provider.")
@click.option("--budget", "-b", is_flag=True, help="Show budget vs actual with threshold warnings.")
@click.option("--json-output", "json_out", is_flag=True, help="Output as JSON.")
def summary(month: str | None, provider: str | None, budget: bool, json_out: bool) -> None:
    """Show cost summary across all configured providers."""
    if not is_cost_tracking_enabled():
        click.echo("Cost tracking is not enabled.")
        click.echo("Run: bin/vibe setup --wizard cost-tracking")
        return

    target_month = month or _current_month()
    config = get_cost_tracking_config()

    reports: list[CostReport] = []
    manual_entries = get_manual_entries()

    if provider:
        # Single provider mode
        with Spinner(f"Fetching costs for {provider}"):
            report = _fetch_provider_report(provider, target_month, config)
        if report:
            reports.append(report)
        else:
            click.echo(f"Could not fetch costs for provider: {provider}")
            return
    else:
        # All providers
        providers = get_all_providers()
        for p in providers:
            with Spinner(f"Fetching costs for {p.display_name}"):
                report = _fetch_provider_report(p.name, target_month, config)
            if report:
                reports.append(report)

    if json_out:
        _print_json(reports, manual_entries, target_month, config)
    else:
        _print_table(reports, manual_entries, target_month, budget, config)


def _print_table(
    reports: list[CostReport],
    manual_entries: list[ManualCostEntry],
    month: str,
    show_budget: bool,
    config: dict,
) -> None:
    """Print a formatted cost summary table."""
    click.echo()
    click.echo(f"Cost Summary ({_month_display(month)})")
    click.echo("\u2550" * 55)

    # Header
    click.echo(f"{'Provider':<20} {'Plan Cost':>10} {'Overage':>10} {'Total':>10}")
    click.echo("\u2500" * 55)

    grand_total = 0.0

    # API-tracked providers
    for report in reports:
        plan_str = _format_cost(report.plan_cost) if report.plan_cost else "\u2014"
        overage_str = _format_cost(report.overage) if report.overage else "\u2014"
        total_str = _format_cost(report.total)
        suffix = "  (estimated)" if report.is_estimated else ""

        click.echo(
            f"{report.provider:<20} {plan_str:>10} {overage_str:>10} {total_str:>10}{suffix}"
        )
        grand_total += report.total

    # Manual entries
    for entry in manual_entries:
        cost = entry.monthly_cost
        label = f"{entry.name} (manual)"
        dash = "\u2014"
        click.echo(f"{label:<20} {_format_cost(cost):>10} {dash:>10} {_format_cost(cost):>10}")
        grand_total += cost

    # Totals
    click.echo("\u2500" * 55)
    click.echo(f"{'Total':<20} {'':>10} {'':>10} {_format_cost(grand_total):>10}")

    # Budget section
    budget_monthly, alert_threshold = get_budget_config()
    if show_budget or budget_monthly > 0:
        _print_budget(grand_total, budget_monthly, alert_threshold)

    click.echo()


def _print_budget(total: float, budget: float, threshold_pct: float) -> None:
    """Print budget comparison section."""
    if budget <= 0:
        click.echo()
        click.echo("No budget set. Run: bin/vibe setup --wizard cost-tracking")
        return

    remaining = budget - total
    pct_used = (total / budget) * 100 if budget > 0 else 0
    color = _color_for_pct(pct_used)

    click.echo(f"{'Budget':<20} {'':>10} {'':>10} {_format_cost(budget):>10}")

    remaining_str = _format_cost(abs(remaining))
    if remaining >= 0:
        label = "Remaining"
        pct_label = f"({pct_used:.0f}% used)"
    else:
        label = "Over budget"
        pct_label = f"({pct_used:.0f}% of budget)"

    warning = ""
    if pct_used >= 95:
        warning = " !!"
    elif pct_used >= threshold_pct:
        warning = " !"

    line = f"{label:<20} {'':>10} {'':>10} {remaining_str:>10} {pct_label}{warning}"
    click.echo(click.style(line, fg=color))


def _print_json(
    reports: list[CostReport],
    manual_entries: list[ManualCostEntry],
    month: str,
    config: dict,
) -> None:
    """Print cost data as JSON."""
    import json

    budget_monthly, alert_threshold = get_budget_config()
    grand_total = sum(r.total for r in reports) + sum(e.monthly_cost for e in manual_entries)

    data = {
        "month": month,
        "total": round(grand_total, 2),
        "budget": budget_monthly,
        "alert_threshold_pct": alert_threshold,
        "providers": [
            {
                "name": r.provider,
                "plan_cost": round(r.plan_cost, 2),
                "overage": round(r.overage, 2),
                "total": round(r.total, 2),
                "is_estimated": r.is_estimated,
            }
            for r in reports
        ],
        "manual": [
            {
                "name": e.name,
                "monthly_cost": round(e.monthly_cost, 2),
                "billing": e.billing,
            }
            for e in manual_entries
        ],
    }
    click.echo(json.dumps(data, indent=2))


# Allow running as `python -m lib.vibe.cli.costs`
if __name__ == "__main__":
    main()
