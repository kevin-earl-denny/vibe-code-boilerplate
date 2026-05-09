"""Vercel billing API cost provider.

Uses the Vercel billing charges API (FOCUS v1.3 format) to pull
actual usage costs with daily granularity.

Env vars:
    VERCEL_TOKEN - Vercel API token (Account Settings > Tokens)
"""

import os
from datetime import datetime

import requests

from lib.vibe.costs.base import CostLineItem, CostProvider, CostReport

VERCEL_API_BASE = "https://api.vercel.com"


class VercelCostProvider(CostProvider):
    """Vercel billing integration via the REST API."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self._token = os.environ.get("VERCEL_TOKEN", "")

    @property
    def name(self) -> str:
        return "vercel"

    @property
    def display_name(self) -> str:
        return "Vercel"

    def get_env_vars(self) -> list[str]:
        return ["VERCEL_TOKEN"]

    def check_credentials(self) -> bool:
        if not self._token:
            return False
        try:
            resp = requests.get(
                f"{VERCEL_API_BASE}/v2/user",
                headers=self._headers(),
                timeout=10,
            )
            return bool(resp.status_code == 200)
        except requests.RequestException:
            return False

    def get_current_costs(self, month: str) -> CostReport:
        """Fetch costs from the Vercel billing charges API.

        Args:
            month: Month in YYYY-MM format.

        Returns:
            CostReport with Vercel costs broken down by service.
        """
        start, end = self._month_range(month)

        try:
            resp = requests.get(
                f"{VERCEL_API_BASE}/billing/charges",
                headers=self._headers(),
                params={"from": start, "to": end},
                timeout=30,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            return CostReport(
                provider=self.display_name,
                total=0.0,
                is_estimated=True,
                raw={"error": str(e)},
            )

        return self._parse_charges(resp.text, month)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _parse_charges(self, body: str, month: str) -> CostReport:
        """Parse FOCUS v1.3 JSONL response into a CostReport."""
        import json

        line_items: list[CostLineItem] = []
        total = 0.0
        service_costs: dict[str, float] = {}

        for line in body.strip().splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            cost = float(record.get("BilledCost", 0))
            service = record.get("ServiceName", "Other")
            quantity = float(record.get("ConsumedQuantity", 0))
            unit = record.get("PricingUnit", "")

            total += cost
            service_costs[service] = service_costs.get(service, 0) + cost

            if cost > 0:
                line_items.append(
                    CostLineItem(name=service, amount=cost, unit=unit, quantity=quantity)
                )

        # Aggregate line items by service
        aggregated: list[CostLineItem] = []
        for service, amount in sorted(service_costs.items(), key=lambda x: -x[1]):
            if amount > 0:
                aggregated.append(CostLineItem(name=service, amount=round(amount, 2)))

        plan_cost = float(self._config.get("plan_cost", 0))
        overage = max(0, total - plan_cost) if plan_cost else 0

        return CostReport(
            provider=self.display_name,
            plan_cost=plan_cost,
            overage=round(overage, 2),
            total=round(total, 2),
            line_items=aggregated,
            raw={"month": month, "service_costs": service_costs},
        )

    @staticmethod
    def _month_range(month: str) -> tuple[str, str]:
        """Convert YYYY-MM to start/end ISO timestamps."""
        dt = datetime.strptime(month, "%Y-%m")
        start = dt.strftime("%Y-%m-01T00:00:00Z")
        # End of month: use first of next month
        if dt.month == 12:
            end_dt = dt.replace(year=dt.year + 1, month=1)
        else:
            end_dt = dt.replace(month=dt.month + 1)
        end = end_dt.strftime("%Y-%m-01T00:00:00Z")
        return start, end
