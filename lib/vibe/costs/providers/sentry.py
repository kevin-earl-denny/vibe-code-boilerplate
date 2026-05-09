"""Sentry event quota monitoring cost provider.

Uses the Sentry API to track event quotas and plan costs.

Env vars:
    SENTRY_AUTH_TOKEN - Sentry auth token (org-level)
    SENTRY_ORG - Sentry organization slug
"""

import os

import requests

from lib.vibe.costs.base import CostLineItem, CostProvider, CostReport

SENTRY_API_BASE = "https://sentry.io/api/0"


class SentryCostProvider(CostProvider):
    """Sentry event quota monitoring."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self._token = os.environ.get("SENTRY_AUTH_TOKEN", "")
        self._org = os.environ.get("SENTRY_ORG", self._config.get("org", ""))

    @property
    def name(self) -> str:
        return "sentry"

    @property
    def display_name(self) -> str:
        return "Sentry"

    def get_env_vars(self) -> list[str]:
        return ["SENTRY_AUTH_TOKEN"]

    def check_credentials(self) -> bool:
        if not self._token:
            return False
        if not self._org:
            return False
        try:
            resp = requests.get(
                f"{SENTRY_API_BASE}/organizations/{self._org}/",
                headers=self._headers(),
                timeout=10,
            )
            return bool(resp.status_code == 200)
        except requests.RequestException:
            return False

    def get_current_costs(self, month: str) -> CostReport:
        plan_cost = float(self._config.get("plan_cost", 0))

        if not self._org:
            return CostReport(
                provider=self.display_name,
                plan_cost=plan_cost,
                total=plan_cost,
                raw={"error": "No SENTRY_ORG configured"},
            )

        # Fetch org stats for event usage
        stats = self._get_org_stats()

        line_items: list[CostLineItem] = []
        if plan_cost > 0:
            line_items.append(CostLineItem(name="Plan", amount=plan_cost))

        events_used = stats.get("events_used", 0)
        events_quota = stats.get("events_quota", 0)

        if events_quota > 0 and events_used > 0:
            pct = (events_used / events_quota) * 100
            line_items.append(
                CostLineItem(
                    name=f"Events ({pct:.0f}% of quota)",
                    amount=0,
                    unit="events",
                    quantity=float(events_used),
                )
            )

        return CostReport(
            provider=self.display_name,
            plan_cost=plan_cost,
            total=plan_cost,
            line_items=line_items,
            raw=stats,
        )

    def _get_org_stats(self) -> dict:
        """Fetch organization usage stats."""
        try:
            resp = requests.get(
                f"{SENTRY_API_BASE}/organizations/{self._org}/stats_v2/",
                headers=self._headers(),
                params={"field": "sum(quantity)", "category": "error", "interval": "1d"},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                total_events = sum(
                    sum(point[1] for point in group.get("series", {}).get("sum(quantity)", []))
                    for group in data.get("groups", [])
                )
                return {"events_used": total_events, "events_quota": 0}
        except requests.RequestException:
            pass
        return {}

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}
