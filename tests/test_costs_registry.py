"""Tests for cost tracking registry."""

import json
from datetime import datetime, timedelta
from unittest.mock import patch

from lib.vibe.costs.base import CostReport
from lib.vibe.costs.registry import (
    get_all_providers,
    get_budget_config,
    get_cached_report,
    get_cost_tracking_config,
    get_enabled_providers,
    get_manual_entries,
    is_cost_tracking_enabled,
    load_provider,
    save_cached_report,
)

SAMPLE_CONFIG = {
    "cost_tracking": {
        "enabled": True,
        "budget_monthly": 200,
        "alert_threshold_pct": 80,
        "providers": {
            "vercel": {"enabled": True},
            "neon": {"enabled": True},
            "fly": {"enabled": False},
            "manual": [
                {"name": "Figma", "cost": 15.00, "billing": "monthly"},
                {"name": "Domains", "cost": 12.00, "billing": "yearly"},
            ],
        },
    }
}


class TestGetCostTrackingConfig:
    def test_returns_section(self):
        result = get_cost_tracking_config(SAMPLE_CONFIG)
        assert result["enabled"] is True
        assert result["budget_monthly"] == 200

    def test_returns_empty_if_missing(self):
        result = get_cost_tracking_config({})
        assert result == {}


class TestIsCostTrackingEnabled:
    def test_enabled(self):
        assert is_cost_tracking_enabled(SAMPLE_CONFIG) is True

    def test_disabled(self):
        config = {"cost_tracking": {"enabled": False}}
        assert is_cost_tracking_enabled(config) is False

    def test_missing(self):
        assert is_cost_tracking_enabled({}) is False


class TestGetEnabledProviders:
    def test_returns_enabled_only(self):
        enabled = get_enabled_providers(SAMPLE_CONFIG)
        assert "vercel" in enabled
        assert "neon" in enabled
        assert "fly" not in enabled

    def test_excludes_manual(self):
        enabled = get_enabled_providers(SAMPLE_CONFIG)
        assert "manual" not in enabled

    def test_empty_config(self):
        assert get_enabled_providers({}) == []


class TestGetManualEntries:
    def test_returns_entries(self):
        entries = get_manual_entries(SAMPLE_CONFIG)
        assert len(entries) == 2
        assert entries[0].name == "Figma"
        assert entries[0].cost == 15.00
        assert entries[1].name == "Domains"
        assert entries[1].billing == "yearly"

    def test_empty_config(self):
        assert get_manual_entries({}) == []


class TestGetBudgetConfig:
    def test_returns_budget(self):
        budget, threshold = get_budget_config(SAMPLE_CONFIG)
        assert budget == 200
        assert threshold == 80

    def test_defaults(self):
        budget, threshold = get_budget_config({})
        assert budget == 0
        assert threshold == 80


class TestLoadProvider:
    def test_unknown_provider(self):
        assert load_provider("nonexistent") is None

    def test_known_provider_loads(self):
        # Provider is registered and module exists
        result = load_provider("vercel")
        assert result is not None
        assert result.name == "vercel"


class TestCacheOperations:
    def test_save_and_load(self, tmp_path):
        cache_dir = tmp_path / "cache"
        report = CostReport(provider="test", plan_cost=10, overage=5, total=15)

        with patch("lib.vibe.costs.registry.CACHE_DIR", cache_dir):
            save_cached_report(report, "2026-02")
            loaded = get_cached_report("test", "2026-02")

        assert loaded is not None
        assert loaded.provider == "test"
        assert loaded.total == 15.0

    def test_cache_miss(self, tmp_path):
        with patch("lib.vibe.costs.registry.CACHE_DIR", tmp_path):
            assert get_cached_report("nonexistent", "2026-02") is None

    def test_expired_cache(self, tmp_path):
        cache_file = tmp_path / "test_2026-02.json"
        old_time = (datetime.now() - timedelta(hours=2)).isoformat()
        cache_file.write_text(
            json.dumps(
                {
                    "provider": "test",
                    "total": 10.0,
                    "cached_at": old_time,
                }
            )
        )

        with patch("lib.vibe.costs.registry.CACHE_DIR", tmp_path):
            assert get_cached_report("test", "2026-02") is None

    def test_corrupted_cache(self, tmp_path):
        cache_file = tmp_path / "test_2026-02.json"
        cache_file.write_text("not json")

        with patch("lib.vibe.costs.registry.CACHE_DIR", tmp_path):
            assert get_cached_report("test", "2026-02") is None


class TestGetAllProviders:
    def test_loads_enabled_providers(self):
        # Should load providers that are enabled in config
        providers = get_all_providers(SAMPLE_CONFIG)
        names = [p.name for p in providers]
        assert "vercel" in names
        assert "neon" in names
