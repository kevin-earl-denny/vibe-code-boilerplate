"""Tests for cost tracking setup wizard."""

from unittest.mock import patch

from lib.vibe.wizards.costs import _should_default_enable, run_costs_wizard


class TestShouldDefaultEnable:
    def test_enabled_in_cost_tracking(self):
        config = {"cost_tracking": {"providers": {"vercel": {"enabled": True}}}}
        assert _should_default_enable("vercel", config) is True

    def test_disabled_in_cost_tracking(self):
        config = {"cost_tracking": {"providers": {"vercel": {"enabled": False}}}}
        assert _should_default_enable("vercel", config) is False

    def test_vercel_deployment_configured(self):
        config = {"deployment": {"vercel": {"enabled": True}}}
        assert _should_default_enable("vercel", config) is True

    def test_fly_deployment_configured(self):
        config = {"deployment": {"fly": {"enabled": True}}}
        assert _should_default_enable("fly", config) is True

    def test_neon_database_configured(self):
        config = {"database": {"neon": {"enabled": True}}}
        assert _should_default_enable("neon", config) is True

    def test_supabase_database_configured(self):
        config = {"database": {"supabase": {"enabled": True}}}
        assert _should_default_enable("supabase", config) is True

    def test_unknown_provider(self):
        assert _should_default_enable("openai", {}) is False


class TestRunCostsWizard:
    def test_non_interactive_fails(self):
        config = {}
        with patch(
            "lib.vibe.wizards.costs.require_interactive", return_value=(False, "Not interactive")
        ):
            result = run_costs_wizard(config)
        assert result is False
