"""Tests for all cost tracking providers."""

from unittest.mock import MagicMock, patch

from lib.vibe.costs.providers.anthropic import AnthropicCostProvider
from lib.vibe.costs.providers.fly import FlyCostProvider
from lib.vibe.costs.providers.github_actions import GitHubActionsCostProvider
from lib.vibe.costs.providers.neon import NeonCostProvider
from lib.vibe.costs.providers.sentry import SentryCostProvider
from lib.vibe.costs.providers.supabase import SupabaseCostProvider


class TestNeonCostProvider:
    def test_name(self):
        p = NeonCostProvider()
        assert p.name == "neon"
        assert p.display_name == "Neon"

    def test_no_credentials(self):
        with patch.dict("os.environ", {}, clear=True):
            p = NeonCostProvider()
            assert p.check_credentials() is False

    @patch("lib.vibe.costs.providers.neon.requests.get")
    def test_get_current_costs(self, mock_get):
        api_response = {
            "projects": [
                {
                    "periods": [
                        {
                            "compute_unit_seconds": 36000,
                            "root_branch_bytes_month": 1073741824,
                        }
                    ]
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with patch.dict("os.environ", {"NEON_API_KEY": "test"}):
            p = NeonCostProvider()
            report = p.get_current_costs("2026-02")

        assert report.provider == "Neon"
        assert report.total > 0
        assert len(report.line_items) > 0


class TestSupabaseCostProvider:
    def test_name(self):
        p = SupabaseCostProvider()
        assert p.name == "supabase"

    def test_default_plan_cost(self):
        assert SupabaseCostProvider._default_plan_cost("free") == 0
        assert SupabaseCostProvider._default_plan_cost("pro") == 25.0
        assert SupabaseCostProvider._default_plan_cost("team") == 599.0

    @patch("lib.vibe.costs.providers.supabase.requests.get")
    def test_get_current_costs(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"slug": "my-org"}]
        mock_resp.raise_for_status = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        with patch.dict("os.environ", {"SUPABASE_ACCESS_TOKEN": "test"}):
            p = SupabaseCostProvider(config={"plan": "pro", "plan_cost": 25.0})
            report = p.get_current_costs("2026-02")

        assert report.plan_cost == 25.0
        assert report.total == 25.0


class TestFlyCostProvider:
    def test_name(self):
        p = FlyCostProvider()
        assert p.name == "fly"
        assert p.is_estimated is True

    def test_check_credentials_with_token(self):
        with patch.dict("os.environ", {"FLY_API_TOKEN": "test"}):
            p = FlyCostProvider()
            assert p.check_credentials() is True

    @patch("lib.vibe.costs.providers.fly.subprocess.run")
    def test_get_machines_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        with patch.dict("os.environ", {"FLY_API_TOKEN": "test"}):
            p = FlyCostProvider()
            report = p.get_current_costs("2026-02")
        assert report.total == 0.0
        assert report.is_estimated is True


class TestGitHubActionsCostProvider:
    def test_name(self):
        p = GitHubActionsCostProvider()
        assert p.name == "github"
        assert p.display_name == "GitHub Actions"

    @patch("lib.vibe.costs.providers.github_actions.subprocess.run")
    def test_parse_usage(self, mock_run):
        p = GitHubActionsCostProvider()
        usage = {
            "total_minutes_used": 100,
            "included_minutes": 2000,
            "total_paid_minutes_used": 0,
            "minutes_used_breakdown": {
                "UBUNTU": 80,
                "MACOS": 10,
                "WINDOWS": 10,
            },
        }
        report = p._parse_usage(usage)
        assert report.total > 0
        assert len(report.line_items) == 3


class TestAnthropicCostProvider:
    def test_name(self):
        p = AnthropicCostProvider()
        assert p.name == "anthropic"
        assert p.is_estimated is True

    def test_estimated_from_config(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            p = AnthropicCostProvider(config={"monthly_estimate": 50.0})
            report = p.get_current_costs("2026-02")
        assert report.total == 50.0
        assert report.is_estimated is True


class TestSentryCostProvider:
    def test_name(self):
        p = SentryCostProvider()
        assert p.name == "sentry"

    def test_no_org_configured(self):
        with patch.dict("os.environ", {"SENTRY_AUTH_TOKEN": "test"}, clear=True):
            p = SentryCostProvider()
            report = p.get_current_costs("2026-02")
        assert report.provider == "Sentry"

    def test_check_credentials_no_token(self):
        with patch.dict("os.environ", {}, clear=True):
            p = SentryCostProvider()
            assert p.check_credentials() is False
