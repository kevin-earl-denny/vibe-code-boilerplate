"""Tests for cost tracking base classes."""

import pytest

from lib.vibe.costs.base import CostLineItem, CostProvider, CostReport, ManualCostEntry


class TestCostLineItem:
    def test_basic_creation(self):
        item = CostLineItem(name="Bandwidth", amount=3.50, unit="GB", quantity=100)
        assert item.name == "Bandwidth"
        assert item.amount == 3.50
        assert item.unit == "GB"
        assert item.quantity == 100

    def test_defaults(self):
        item = CostLineItem(name="API calls", amount=1.00)
        assert item.unit == ""
        assert item.quantity == 0.0


class TestCostReport:
    def test_basic_creation(self):
        report = CostReport(
            provider="vercel",
            plan_cost=20.0,
            overage=5.0,
            total=25.0,
        )
        assert report.provider == "vercel"
        assert report.plan_cost == 20.0
        assert report.overage == 5.0
        assert report.total == 25.0
        assert report.is_estimated is False
        assert report.currency == "USD"
        assert report.line_items == []
        assert report.raw == {}

    def test_with_line_items(self):
        items = [CostLineItem(name="Bandwidth", amount=2.0)]
        report = CostReport(provider="vercel", total=2.0, line_items=items)
        assert len(report.line_items) == 1
        assert report.line_items[0].name == "Bandwidth"

    def test_estimated(self):
        report = CostReport(provider="fly", total=14.82, is_estimated=True)
        assert report.is_estimated is True


class TestManualCostEntry:
    def test_monthly_billing(self):
        entry = ManualCostEntry(name="Figma", cost=15.00, billing="monthly")
        assert entry.monthly_cost == 15.00

    def test_yearly_billing(self):
        entry = ManualCostEntry(name="Domains", cost=12.00, billing="yearly")
        assert entry.monthly_cost == 1.00

    def test_default_billing(self):
        entry = ManualCostEntry(name="Tool", cost=10.00)
        assert entry.billing == "monthly"
        assert entry.monthly_cost == 10.00


class TestCostProviderABC:
    """Test that CostProvider enforces the abstract interface."""

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            CostProvider()  # type: ignore[abstract]

    def test_concrete_implementation(self):
        class FakeProvider(CostProvider):
            @property
            def name(self) -> str:
                return "fake"

            def check_credentials(self) -> bool:
                return True

            def get_current_costs(self, month: str) -> CostReport:
                return CostReport(provider="Fake", total=10.0)

        p = FakeProvider()
        assert p.name == "fake"
        assert p.display_name == "Fake"
        assert p.is_estimated is False
        assert p.check_credentials() is True
        report = p.get_current_costs("2026-02")
        assert report.total == 10.0

    def test_validate_config_passes(self):
        class GoodProvider(CostProvider):
            @property
            def name(self) -> str:
                return "good"

            def check_credentials(self) -> bool:
                return True

            def get_current_costs(self, month: str) -> CostReport:
                return CostReport(provider="Good", total=0)

        p = GoodProvider()
        valid, issues = p.validate_config()
        assert valid is True
        assert issues == []

    def test_validate_config_fails(self):
        class BadProvider(CostProvider):
            @property
            def name(self) -> str:
                return "bad"

            def check_credentials(self) -> bool:
                return False

            def get_env_vars(self) -> list[str]:
                return ["BAD_API_KEY"]

            def get_current_costs(self, month: str) -> CostReport:
                return CostReport(provider="Bad", total=0)

        p = BadProvider()
        valid, issues = p.validate_config()
        assert valid is False
        assert "BAD_API_KEY" in issues[0]

    def test_display_name_default(self):
        class LowerProvider(CostProvider):
            @property
            def name(self) -> str:
                return "openai"

            def check_credentials(self) -> bool:
                return True

            def get_current_costs(self, month: str) -> CostReport:
                return CostReport(provider="OpenAI", total=0)

        p = LowerProvider()
        assert p.display_name == "Openai"

    def test_get_env_vars_default(self):
        class MinimalProvider(CostProvider):
            @property
            def name(self) -> str:
                return "minimal"

            def check_credentials(self) -> bool:
                return True

            def get_current_costs(self, month: str) -> CostReport:
                return CostReport(provider="Minimal", total=0)

        p = MinimalProvider()
        assert p.get_env_vars() == []
