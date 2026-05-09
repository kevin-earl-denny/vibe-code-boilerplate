"""OpenAI API usage cost provider.

Uses the OpenAI usage API to track token consumption and costs.

Env vars:
    OPENAI_API_KEY - OpenAI API key
"""

import os
from datetime import datetime

import requests

from lib.vibe.costs.base import CostLineItem, CostProvider, CostReport

OPENAI_API_BASE = "https://api.openai.com/v1"


class OpenAICostProvider(CostProvider):
    """OpenAI API usage tracking."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self._token = os.environ.get("OPENAI_API_KEY", "")

    @property
    def name(self) -> str:
        return "openai"

    @property
    def display_name(self) -> str:
        return "OpenAI"

    def get_env_vars(self) -> list[str]:
        return ["OPENAI_API_KEY"]

    def check_credentials(self) -> bool:
        if not self._token:
            return False
        try:
            resp = requests.get(
                f"{OPENAI_API_BASE}/models",
                headers=self._headers(),
                timeout=10,
            )
            return bool(resp.status_code == 200)
        except requests.RequestException:
            return False

    def get_current_costs(self, month: str) -> CostReport:
        start_date, end_date = self._month_range(month)

        try:
            resp = requests.get(
                "https://api.openai.com/v1/organization/costs",
                headers=self._headers(),
                params={"start_time": start_date, "end_time": end_date, "limit": 30},
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

        return self._parse_costs(data)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _parse_costs(self, data: dict) -> CostReport:
        """Parse OpenAI costs response."""
        line_items: list[CostLineItem] = []
        total = 0.0

        for bucket in data.get("data", []):
            for result in bucket.get("results", []):
                amount = float(result.get("amount", {}).get("value", 0))
                if amount > 0:
                    line_items.append(
                        CostLineItem(
                            name=result.get("line_item", "API Usage"),
                            amount=round(amount / 100, 2),  # cents to dollars
                        )
                    )
                    total += amount / 100

        return CostReport(
            provider=self.display_name,
            total=round(total, 2),
            line_items=line_items,
            raw=data,
        )

    @staticmethod
    def _month_range(month: str) -> tuple[int, int]:
        """Convert YYYY-MM to Unix timestamps."""
        dt = datetime.strptime(month, "%Y-%m")
        start = int(dt.timestamp())
        if dt.month == 12:
            end_dt = dt.replace(year=dt.year + 1, month=1)
        else:
            end_dt = dt.replace(month=dt.month + 1)
        end = int(end_dt.timestamp())
        return start, end
