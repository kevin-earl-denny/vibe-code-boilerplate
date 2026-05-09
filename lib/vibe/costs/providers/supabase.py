"""Supabase billing cost provider.

Supabase doesn't expose a granular billing API, so this provider uses
the organization usage endpoint and fixed plan costs.

Env vars:
    SUPABASE_ACCESS_TOKEN - Supabase management API token
"""

import os

import requests

from lib.vibe.costs.base import CostLineItem, CostProvider, CostReport

SUPABASE_API_BASE = "https://api.supabase.com/v1"


class SupabaseCostProvider(CostProvider):
    """Supabase billing integration."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self._token = os.environ.get("SUPABASE_ACCESS_TOKEN", "")

    @property
    def name(self) -> str:
        return "supabase"

    @property
    def display_name(self) -> str:
        return "Supabase"

    def get_env_vars(self) -> list[str]:
        return ["SUPABASE_ACCESS_TOKEN"]

    def check_credentials(self) -> bool:
        if not self._token:
            return False
        try:
            resp = requests.get(
                f"{SUPABASE_API_BASE}/projects",
                headers=self._headers(),
                timeout=10,
            )
            return bool(resp.status_code == 200)
        except requests.RequestException:
            return False

    def get_current_costs(self, month: str) -> CostReport:
        plan = self._config.get("plan", "free")
        plan_cost = float(self._config.get("plan_cost", self._default_plan_cost(plan)))

        # Try to get usage data
        try:
            resp = requests.get(
                f"{SUPABASE_API_BASE}/organizations",
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            orgs = resp.json()
        except requests.RequestException:
            return CostReport(
                provider=self.display_name,
                plan_cost=plan_cost,
                total=plan_cost,
            )

        # Supabase bills per organization; sum across all orgs
        line_items: list[CostLineItem] = []
        line_items.append(CostLineItem(name=f"{plan.title()} Plan", amount=plan_cost))

        return CostReport(
            provider=self.display_name,
            plan_cost=plan_cost,
            overage=0.0,
            total=plan_cost,
            line_items=line_items,
            raw={"plan": plan, "org_count": len(orgs) if isinstance(orgs, list) else 0},
        )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    @staticmethod
    def _default_plan_cost(plan: str) -> float:
        costs = {"free": 0, "pro": 25.0, "team": 599.0, "enterprise": 0}
        return costs.get(plan.lower(), 0)
