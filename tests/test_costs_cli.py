"""Tests for cost tracking CLI commands."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from lib.vibe.cli.costs import main
from lib.vibe.costs.base import ManualCostEntry


@pytest.fixture
def runner():
    return CliRunner()


def _mock_enabled(config=None):
    return True


def _mock_disabled(config=None):
    return False


class TestCostsSummaryCommand:
    def test_not_enabled(self, runner):
        with patch("lib.vibe.cli.costs.is_cost_tracking_enabled", return_value=False):
            result = runner.invoke(main, ["summary"])
        assert result.exit_code == 0
        assert "not enabled" in result.output.lower()

    def test_summary_with_providers(self, runner):
        with (
            patch("lib.vibe.cli.costs.is_cost_tracking_enabled", return_value=True),
            patch("lib.vibe.cli.costs.get_cost_tracking_config", return_value={"providers": {}}),
            patch("lib.vibe.cli.costs.get_all_providers", return_value=[]),
            patch("lib.vibe.cli.costs.get_manual_entries", return_value=[]),
            patch("lib.vibe.cli.costs.get_budget_config", return_value=(0, 80)),
        ):
            result = runner.invoke(main, ["summary"])
        assert result.exit_code == 0
        assert "Cost Summary" in result.output

    def test_summary_json_output(self, runner):
        with (
            patch("lib.vibe.cli.costs.is_cost_tracking_enabled", return_value=True),
            patch("lib.vibe.cli.costs.get_cost_tracking_config", return_value={"providers": {}}),
            patch("lib.vibe.cli.costs.get_all_providers", return_value=[]),
            patch("lib.vibe.cli.costs.get_manual_entries", return_value=[]),
            patch("lib.vibe.cli.costs.get_budget_config", return_value=(200, 80)),
        ):
            result = runner.invoke(main, ["summary", "--json-output"])
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert "month" in data
        assert "total" in data
        assert data["budget"] == 200

    def test_summary_with_manual_entries(self, runner):
        entries = [
            ManualCostEntry(name="Figma", cost=15.0, billing="monthly"),
            ManualCostEntry(name="Domains", cost=12.0, billing="yearly"),
        ]

        with (
            patch("lib.vibe.cli.costs.is_cost_tracking_enabled", return_value=True),
            patch("lib.vibe.cli.costs.get_cost_tracking_config", return_value={"providers": {}}),
            patch("lib.vibe.cli.costs.get_all_providers", return_value=[]),
            patch("lib.vibe.cli.costs.get_manual_entries", return_value=entries),
            patch("lib.vibe.cli.costs.get_budget_config", return_value=(0, 80)),
        ):
            result = runner.invoke(main, ["summary"])
        assert result.exit_code == 0
        assert "Figma" in result.output
        assert "Domains" in result.output
