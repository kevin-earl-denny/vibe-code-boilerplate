"""Tests for cost alerting module."""

from lib.vibe.costs.alerts import check_budget_alerts, project_end_of_month
from lib.vibe.costs.base import CostReport


class TestCheckBudgetAlerts:
    def test_no_budget(self):
        reports = [CostReport(provider="Test", total=100)]
        alerts = check_budget_alerts(reports, budget=0)
        assert alerts == []

    def test_under_threshold(self):
        reports = [CostReport(provider="Test", total=50)]
        alerts = check_budget_alerts(reports, budget=200, threshold_pct=80)
        assert alerts == []

    def test_warning_threshold(self):
        reports = [CostReport(provider="Test", total=170)]
        alerts = check_budget_alerts(reports, budget=200, threshold_pct=80)
        assert len(alerts) == 1
        assert alerts[0].level == "warning"
        assert alerts[0].pct == 85.0

    def test_critical_threshold(self):
        reports = [CostReport(provider="Test", total=195)]
        alerts = check_budget_alerts(reports, budget=200, threshold_pct=80)
        assert len(alerts) == 1
        assert alerts[0].level == "critical"

    def test_per_provider_threshold(self):
        reports = [
            CostReport(provider="OpenAI", total=140),
            CostReport(provider="Vercel", total=10),
        ]
        alerts = check_budget_alerts(
            reports,
            budget=500,
            threshold_pct=80,
            provider_thresholds={"OpenAI": 150},
        )
        # Total is under budget (150/500 = 30%), but OpenAI is at 93% of its limit
        assert len(alerts) == 1
        assert alerts[0].provider == "OpenAI"
        assert alerts[0].level == "warning"

    def test_multiple_alerts(self):
        reports = [
            CostReport(provider="OpenAI", total=148),
            CostReport(provider="Vercel", total=45),
        ]
        alerts = check_budget_alerts(
            reports,
            budget=200,
            threshold_pct=80,
            provider_thresholds={"OpenAI": 150, "Vercel": 50},
        )
        # Total: 193/200 = 96.5% (critical)
        # OpenAI: 148/150 = 98.7% (critical)
        # Vercel: 45/50 = 90% (warning)
        assert len(alerts) == 3
        critical = [a for a in alerts if a.level == "critical"]
        assert len(critical) == 2


class TestProjectEndOfMonth:
    def test_historical_month_returns_actual(self):
        result = project_end_of_month(100.0, "2020-01")
        assert result == 100.0

    def test_zero_spend(self):
        result = project_end_of_month(0.0, "2020-01")
        assert result == 0.0
