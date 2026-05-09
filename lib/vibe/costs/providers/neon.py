"""Neon consumption API cost provider.

Uses the Neon Consumption API v2 to track compute, storage,
and data transfer costs with daily granularity.

Env vars:
    NEON_API_KEY - Neon API key (Console > Account > API Keys)
"""

import os
from datetime import datetime

import requests

from lib.vibe.costs.base import CostLineItem, CostProvider, CostReport

NEON_API_BASE = "https://console.neon.tech/api/v2"

# Default rate card (Launch plan)
DEFAULT_RATES: dict[str, float] = {
    "compute_unit_seconds": 0.16 / 3600,  # $0.16/CU-hour -> per second
    "root_branch_bytes_month": 0.000000000125,  # ~$0.125/GiB-month
    "child_branch_bytes_month": 0.000000000125,
    "instant_restore_bytes_month": 0.000000000125,
    "public_network_transfer_bytes": 0.00000000009,  # ~$0.09/GiB
    "private_network_transfer_bytes": 0.0,
}


class NeonCostProvider(CostProvider):
    """Neon consumption API integration."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self._token = os.environ.get("NEON_API_KEY", "")

    @property
    def name(self) -> str:
        return "neon"

    @property
    def display_name(self) -> str:
        return "Neon"

    def get_env_vars(self) -> list[str]:
        return ["NEON_API_KEY"]

    def check_credentials(self) -> bool:
        if not self._token:
            return False
        try:
            resp = requests.get(
                f"{NEON_API_BASE}/projects",
                headers=self._headers(),
                params={"limit": 1},
                timeout=10,
            )
            return bool(resp.status_code == 200)
        except requests.RequestException:
            return False

    def get_current_costs(self, month: str) -> CostReport:
        start, end = self._month_range(month)
        metrics = ",".join(DEFAULT_RATES.keys())

        try:
            resp = requests.get(
                f"{NEON_API_BASE}/consumption_history/v2/projects",
                headers=self._headers(),
                params={
                    "from": start,
                    "to": end,
                    "granularity": "monthly",
                    "metrics": metrics,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            return CostReport(
                provider=self.display_name,
                total=0.0,
                is_estimated=True,
                raw={"error": str(e)},
            )

        return self._parse_consumption(data, month)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _parse_consumption(self, data: dict, month: str) -> CostReport:
        """Calculate costs from consumption metrics using rate card."""
        line_items: list[CostLineItem] = []
        total = 0.0
        rates = dict(DEFAULT_RATES)

        projects = data.get("projects", [])
        metric_totals: dict[str, float] = {}

        for project in projects:
            for period in project.get("periods", []):
                for metric_name, rate in rates.items():
                    value = float(period.get(metric_name, 0))
                    metric_totals[metric_name] = metric_totals.get(metric_name, 0) + value

        for metric_name, value in metric_totals.items():
            rate = rates.get(metric_name, 0)
            cost = value * rate
            if cost > 0.005:  # Skip sub-penny amounts
                display = metric_name.replace("_", " ").title()
                line_items.append(CostLineItem(name=display, amount=round(cost, 2), quantity=value))
                total += cost

        plan_cost = float(self._config.get("plan_cost", 0))
        overage = max(0, total - plan_cost) if plan_cost else 0

        return CostReport(
            provider=self.display_name,
            plan_cost=plan_cost,
            overage=round(overage, 2),
            total=round(total, 2),
            line_items=line_items,
            raw={"month": month, "metric_totals": metric_totals},
        )

    @staticmethod
    def _month_range(month: str) -> tuple[str, str]:
        dt = datetime.strptime(month, "%Y-%m")
        start = dt.strftime("%Y-%m-01T00:00:00Z")
        if dt.month == 12:
            end_dt = dt.replace(year=dt.year + 1, month=1)
        else:
            end_dt = dt.replace(month=dt.month + 1)
        end = end_dt.strftime("%Y-%m-01T00:00:00Z")
        return start, end
