"""Fly.io cost estimation provider.

Fly.io doesn't have a billing API, so this provider estimates costs
from machine specs using `fly` CLI or the Machines API.

Env vars:
    FLY_API_TOKEN - Fly.io API token (optional, falls back to fly CLI auth)
"""

import os
import subprocess

from lib.vibe.costs.base import CostLineItem, CostProvider, CostReport

# Approximate pricing per VM size (monthly, shared-cpu)
FLY_PRICING: dict[str, float] = {
    "shared-cpu-1x": 1.94,
    "shared-cpu-2x": 3.88,
    "shared-cpu-4x": 7.76,
    "shared-cpu-8x": 15.52,
    "performance-1x": 29.00,
    "performance-2x": 58.00,
    "performance-4x": 116.00,
    "performance-8x": 232.00,
}


class FlyCostProvider(CostProvider):
    """Fly.io cost estimation via CLI/API."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self._token = os.environ.get("FLY_API_TOKEN", "")

    @property
    def name(self) -> str:
        return "fly"

    @property
    def display_name(self) -> str:
        return "Fly.io"

    @property
    def is_estimated(self) -> bool:
        return True

    def get_env_vars(self) -> list[str]:
        return ["FLY_API_TOKEN"]

    def check_credentials(self) -> bool:
        if self._token:
            return True
        # Fall back to fly CLI auth
        try:
            result = subprocess.run(
                ["fly", "auth", "whoami"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def get_current_costs(self, month: str) -> CostReport:
        """Estimate costs from running machines."""
        machines = self._get_machines()
        line_items: list[CostLineItem] = []
        total = 0.0

        for machine in machines:
            size = machine.get("size", "shared-cpu-1x")
            app = machine.get("app", "unknown")
            cost = FLY_PRICING.get(size, 1.94)
            line_items.append(CostLineItem(name=f"{app} ({size})", amount=cost, unit="machine"))
            total += cost

        return CostReport(
            provider=self.display_name,
            total=round(total, 2),
            is_estimated=True,
            line_items=line_items,
            raw={"machine_count": len(machines)},
        )

    def _get_machines(self) -> list[dict]:
        """Get running machines from fly CLI."""
        try:
            result = subprocess.run(
                ["fly", "machines", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                return []
            import json

            machines = json.loads(result.stdout)
            return [
                {
                    "app": m.get("app_name", "unknown"),
                    "size": m.get("config", {}).get("guest", {}).get("cpu_kind", "shared")
                    + "-cpu-"
                    + str(m.get("config", {}).get("guest", {}).get("cpus", 1))
                    + "x",
                }
                for m in machines
                if m.get("state") == "started"
            ]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []
