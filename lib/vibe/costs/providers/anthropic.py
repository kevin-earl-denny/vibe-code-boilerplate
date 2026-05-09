"""Anthropic API usage cost provider.

Uses manual tracking since Anthropic's API doesn't have a
billing/usage endpoint. Costs are estimated from API headers
or config-provided amounts.

Env vars:
    ANTHROPIC_API_KEY - Anthropic API key
"""

import os

import requests

from lib.vibe.costs.base import CostLineItem, CostProvider, CostReport

ANTHROPIC_API_BASE = "https://api.anthropic.com"


class AnthropicCostProvider(CostProvider):
    """Anthropic API usage tracking."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self._token = os.environ.get("ANTHROPIC_API_KEY", "")

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def display_name(self) -> str:
        return "Anthropic"

    @property
    def is_estimated(self) -> bool:
        return True

    def get_env_vars(self) -> list[str]:
        return ["ANTHROPIC_API_KEY"]

    def check_credentials(self) -> bool:
        if not self._token:
            return False
        try:
            resp = requests.get(
                f"{ANTHROPIC_API_BASE}/v1/models",
                headers=self._headers(),
                timeout=10,
            )
            # 200 or 401 means the endpoint exists (401 = bad key but reachable)
            return bool(resp.status_code == 200)
        except requests.RequestException:
            return False

    def get_current_costs(self, month: str) -> CostReport:
        """Return estimated costs from config.

        Anthropic doesn't have a billing API, so costs must be configured
        manually or estimated from usage logs.
        """
        monthly_estimate = float(self._config.get("monthly_estimate", 0))

        line_items: list[CostLineItem] = []
        if monthly_estimate > 0:
            line_items.append(CostLineItem(name="API Usage (estimated)", amount=monthly_estimate))

        return CostReport(
            provider=self.display_name,
            total=monthly_estimate,
            is_estimated=True,
            line_items=line_items,
            raw={"month": month, "source": "config_estimate"},
        )

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._token,
            "anthropic-version": "2023-06-01",
        }
