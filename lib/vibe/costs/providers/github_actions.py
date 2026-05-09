"""GitHub Actions billing cost provider.

Uses the GitHub billing API to fetch Actions usage minutes
and calculate costs based on runner type.

Env vars:
    GITHUB_TOKEN - GitHub personal access token (or gh CLI auth)
"""

import os
import subprocess

from lib.vibe.costs.base import CostLineItem, CostProvider, CostReport

# Per-minute pricing by runner OS
MINUTE_RATES: dict[str, float] = {
    "UBUNTU": 0.008,
    "MACOS": 0.08,
    "WINDOWS": 0.016,
}


class GitHubActionsCostProvider(CostProvider):
    """GitHub Actions billing integration via gh CLI."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}

    @property
    def name(self) -> str:
        return "github"

    @property
    def display_name(self) -> str:
        return "GitHub Actions"

    def get_env_vars(self) -> list[str]:
        return ["GITHUB_TOKEN"]

    def check_credentials(self) -> bool:
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            return True
        # Fall back to gh CLI auth
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def get_current_costs(self, month: str) -> CostReport:
        """Fetch GitHub Actions billing data."""
        owner = self._config.get("owner", "")
        if not owner:
            owner = self._detect_owner()

        if not owner:
            return CostReport(
                provider=self.display_name,
                total=0.0,
                is_estimated=True,
                raw={"error": "No GitHub owner configured"},
            )

        usage = self._get_billing_usage(owner)
        return self._parse_usage(usage)

    def _detect_owner(self) -> str:
        """Try to detect the repo owner from git remote."""
        try:
            result = subprocess.run(
                ["gh", "repo", "view", "--json", "owner", "-q", ".owner.login"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return ""

    def _get_billing_usage(self, owner: str) -> dict:
        """Fetch billing usage via gh API."""
        import json

        try:
            result = subprocess.run(
                ["gh", "api", f"/orgs/{owner}/settings/billing/actions"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                data: dict = json.loads(result.stdout)
                return data

            # Try user endpoint
            result = subprocess.run(
                ["gh", "api", f"/users/{owner}/settings/billing/actions"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                user_data: dict = json.loads(result.stdout)
                return user_data
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return {}

    def _parse_usage(self, usage: dict) -> CostReport:
        """Parse GitHub billing API response into CostReport."""
        line_items: list[CostLineItem] = []
        total = 0.0

        minutes_breakdown = usage.get("minutes_used_breakdown", {})
        for os_name, minutes in minutes_breakdown.items():
            rate = MINUTE_RATES.get(os_name.upper(), 0.008)
            cost = float(minutes) * rate
            if cost > 0:
                line_items.append(
                    CostLineItem(
                        name=f"{os_name.title()} runners",
                        amount=round(cost, 2),
                        unit="minutes",
                        quantity=float(minutes),
                    )
                )
                total += cost

        included = usage.get("included_minutes", 0)
        total_minutes = usage.get("total_minutes_used", 0)

        return CostReport(
            provider=self.display_name,
            total=round(total, 2),
            line_items=line_items,
            raw={
                "included_minutes": included,
                "total_minutes_used": total_minutes,
                "paid_minutes_used": usage.get("total_paid_minutes_used", 0),
            },
        )
