"""Cost alerting and budget enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from lib.vibe.costs.base import CostReport


@dataclass
class CostAlert:
    """A single cost alert."""

    provider: str
    level: str  # "warning", "critical"
    message: str
    current: float
    limit: float
    pct: float


def check_budget_alerts(
    reports: list[CostReport],
    budget: float,
    threshold_pct: float = 80,
    provider_thresholds: dict[str, float] | None = None,
) -> list[CostAlert]:
    """Check all reports against budget thresholds.

    Args:
        reports: List of cost reports from providers.
        budget: Monthly budget in USD.
        threshold_pct: Default alert threshold percentage.
        provider_thresholds: Optional per-provider threshold overrides.

    Returns:
        List of CostAlert objects for any breached thresholds.
    """
    alerts: list[CostAlert] = []
    provider_thresholds = provider_thresholds or {}

    if budget <= 0:
        return alerts

    # Check total budget
    total = sum(r.total for r in reports)
    total_pct = (total / budget) * 100

    if total_pct >= 95:
        alerts.append(
            CostAlert(
                provider="Total",
                level="critical",
                message=f"Total spend ${total:,.2f} is {total_pct:.0f}% of ${budget:,.2f} budget",
                current=total,
                limit=budget,
                pct=total_pct,
            )
        )
    elif total_pct >= threshold_pct:
        alerts.append(
            CostAlert(
                provider="Total",
                level="warning",
                message=f"Total spend ${total:,.2f} is {total_pct:.0f}% of ${budget:,.2f} budget",
                current=total,
                limit=budget,
                pct=total_pct,
            )
        )

    # Check per-provider thresholds
    for report in reports:
        prov_threshold = provider_thresholds.get(report.provider, 0)
        if prov_threshold > 0:
            prov_pct = (report.total / prov_threshold) * 100
            if prov_pct >= 95:
                alerts.append(
                    CostAlert(
                        provider=report.provider,
                        level="critical",
                        message=f"{report.provider}: ${report.total:,.2f} / ${prov_threshold:,.2f} ({prov_pct:.0f}%)",
                        current=report.total,
                        limit=prov_threshold,
                        pct=prov_pct,
                    )
                )
            elif prov_pct >= threshold_pct:
                alerts.append(
                    CostAlert(
                        provider=report.provider,
                        level="warning",
                        message=f"{report.provider}: ${report.total:,.2f} / ${prov_threshold:,.2f} ({prov_pct:.0f}%)",
                        current=report.total,
                        limit=prov_threshold,
                        pct=prov_pct,
                    )
                )

    return alerts


def project_end_of_month(total_spend: float, month: str | None = None) -> float:
    """Project end-of-month spend based on daily burn rate.

    Args:
        total_spend: Total spend so far this month.
        month: Month in YYYY-MM format (defaults to current).

    Returns:
        Projected total spend for the full month.
    """
    now = datetime.now()

    if month:
        try:
            month_dt = datetime.strptime(month, "%Y-%m")
        except ValueError:
            month_dt = now
    else:
        month_dt = now

    # Days elapsed in the month
    if month_dt.year == now.year and month_dt.month == now.month:
        days_elapsed = now.day
    else:
        # Historical month — return actual total
        return total_spend

    # Days in the month
    if month_dt.month == 12:
        next_month = month_dt.replace(year=month_dt.year + 1, month=1)
    else:
        next_month = month_dt.replace(month=month_dt.month + 1)
    days_in_month = (next_month - month_dt.replace(day=1)).days

    if days_elapsed <= 0:
        return total_spend

    daily_rate = total_spend / days_elapsed
    return round(daily_rate * days_in_month, 2)
