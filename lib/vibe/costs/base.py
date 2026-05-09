"""Abstract base class for cost tracking providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CostLineItem:
    """A single line item in a cost report."""

    name: str
    amount: float
    unit: str = ""  # e.g., "GB", "requests", "minutes"
    quantity: float = 0.0


@dataclass
class CostReport:
    """Cost report from a single provider for a given period."""

    provider: str
    plan_cost: float = 0.0
    overage: float = 0.0
    total: float = 0.0
    is_estimated: bool = False
    line_items: list[CostLineItem] = field(default_factory=list)
    currency: str = "USD"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ManualCostEntry:
    """A manually-entered fixed cost (e.g., Figma, domains)."""

    name: str
    cost: float
    billing: str = "monthly"  # "monthly" or "yearly"

    @property
    def monthly_cost(self) -> float:
        """Return the cost normalized to a monthly amount."""
        if self.billing == "yearly":
            return self.cost / 12
        return self.cost


class CostProvider(ABC):
    """Abstract base class for cost tracking provider integrations."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name (e.g., 'vercel', 'fly')."""

    @property
    def display_name(self) -> str:
        """Return a human-readable display name."""
        return self.name.title()

    @property
    def is_estimated(self) -> bool:
        """Return True if this provider's costs are estimates."""
        return False

    @abstractmethod
    def check_credentials(self) -> bool:
        """Check that required credentials/API keys are available."""

    @abstractmethod
    def get_current_costs(self, month: str) -> CostReport:
        """Fetch costs for a given month.

        Args:
            month: Month in YYYY-MM format (e.g., '2026-02').

        Returns:
            CostReport with the provider's costs for that month.
        """

    def get_env_vars(self) -> list[str]:
        """Return list of required environment variable names."""
        return []

    def validate_config(self) -> tuple[bool, list[str]]:
        """Validate provider configuration.

        Returns:
            Tuple of (is_valid, list of issues).
        """
        issues: list[str] = []
        if not self.check_credentials():
            missing = self.get_env_vars()
            if missing:
                issues.append(f"Missing credentials: {', '.join(missing)}")
            else:
                issues.append("Credentials check failed")
        return len(issues) == 0, issues
