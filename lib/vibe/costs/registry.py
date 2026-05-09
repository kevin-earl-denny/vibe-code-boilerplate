"""Provider registry for cost tracking."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.vibe.config import load_config
from lib.vibe.costs.base import CostProvider, CostReport, ManualCostEntry

# Map of provider name -> (module_path, class_name)
PROVIDER_REGISTRY: dict[str, tuple[str, str]] = {
    "vercel": ("lib.vibe.costs.providers.vercel", "VercelCostProvider"),
    "neon": ("lib.vibe.costs.providers.neon", "NeonCostProvider"),
    "supabase": ("lib.vibe.costs.providers.supabase", "SupabaseCostProvider"),
    "fly": ("lib.vibe.costs.providers.fly", "FlyCostProvider"),
    "github": ("lib.vibe.costs.providers.github_actions", "GitHubActionsCostProvider"),
    "openai": ("lib.vibe.costs.providers.openai", "OpenAICostProvider"),
    "anthropic": ("lib.vibe.costs.providers.anthropic", "AnthropicCostProvider"),
    "sentry": ("lib.vibe.costs.providers.sentry", "SentryCostProvider"),
}

CACHE_DIR = Path(".vibe/cache/costs")
CACHE_TTL_SECONDS = 3600  # 1 hour


def get_cost_tracking_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Get the cost_tracking section from config."""
    if config is None:
        config = load_config()
    result: dict[str, Any] = config.get("cost_tracking", {})
    return result


def is_cost_tracking_enabled(config: dict[str, Any] | None = None) -> bool:
    """Check if cost tracking is enabled in config."""
    ct = get_cost_tracking_config(config)
    return bool(ct.get("enabled", False))


def get_enabled_providers(config: dict[str, Any] | None = None) -> list[str]:
    """Return list of enabled provider names from config."""
    ct = get_cost_tracking_config(config)
    providers = ct.get("providers", {})
    enabled = []
    for name, provider_config in providers.items():
        if name == "manual":
            continue
        if isinstance(provider_config, dict) and provider_config.get("enabled", False):
            enabled.append(name)
    return enabled


def get_manual_entries(config: dict[str, Any] | None = None) -> list[ManualCostEntry]:
    """Return list of manual cost entries from config."""
    ct = get_cost_tracking_config(config)
    providers = ct.get("providers", {})
    manual_list = providers.get("manual", [])
    entries = []
    for entry in manual_list:
        if isinstance(entry, dict):
            entries.append(
                ManualCostEntry(
                    name=entry.get("name", "Unknown"),
                    cost=float(entry.get("cost", 0)),
                    billing=entry.get("billing", "monthly"),
                )
            )
    return entries


def load_provider(name: str, provider_config: dict[str, Any] | None = None) -> CostProvider | None:
    """Dynamically load and instantiate a cost provider.

    Args:
        name: Provider name (must be in PROVIDER_REGISTRY).
        provider_config: Optional provider-specific config dict.

    Returns:
        CostProvider instance or None if provider cannot be loaded.
    """
    if name not in PROVIDER_REGISTRY:
        return None

    module_path, class_name = PROVIDER_REGISTRY[name]
    try:
        import importlib

        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        if provider_config:
            instance: CostProvider = cls(config=provider_config)
        else:
            instance = cls()
        return instance
    except (ImportError, AttributeError):
        return None


def get_all_providers(config: dict[str, Any] | None = None) -> list[CostProvider]:
    """Load all enabled cost providers.

    Returns:
        List of instantiated CostProvider objects.
    """
    if config is None:
        config = load_config()
    ct = get_cost_tracking_config(config)
    providers_config = ct.get("providers", {})
    providers: list[CostProvider] = []

    for name in get_enabled_providers(config):
        provider_cfg = providers_config.get(name, {})
        provider = load_provider(name, provider_cfg if isinstance(provider_cfg, dict) else None)
        if provider is not None:
            providers.append(provider)

    return providers


def get_cached_report(provider_name: str, month: str) -> CostReport | None:
    """Load a cached cost report if it exists and is fresh."""
    cache_file = CACHE_DIR / f"{provider_name}_{month}.json"
    if not cache_file.exists():
        return None

    try:
        data = json.loads(cache_file.read_text())
        cached_at = datetime.fromisoformat(data.get("cached_at", ""))
        age = (datetime.now() - cached_at).total_seconds()
        if age > CACHE_TTL_SECONDS:
            return None

        return CostReport(
            provider=data["provider"],
            plan_cost=data.get("plan_cost", 0.0),
            overage=data.get("overage", 0.0),
            total=data.get("total", 0.0),
            is_estimated=data.get("is_estimated", False),
            currency=data.get("currency", "USD"),
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def save_cached_report(report: CostReport, month: str) -> None:
    """Save a cost report to the cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{report.provider}_{month}.json"
    data = {
        "provider": report.provider,
        "plan_cost": report.plan_cost,
        "overage": report.overage,
        "total": report.total,
        "is_estimated": report.is_estimated,
        "currency": report.currency,
        "cached_at": datetime.now().isoformat(),
    }
    cache_file.write_text(json.dumps(data, indent=2))


def get_budget_config(config: dict[str, Any] | None = None) -> tuple[float, float]:
    """Return (budget_monthly, alert_threshold_pct) from config.

    Returns:
        Tuple of (budget, threshold_pct). Budget is 0 if not set.
    """
    ct = get_cost_tracking_config(config)
    budget = float(ct.get("budget_monthly", 0))
    threshold = float(ct.get("alert_threshold_pct", 80))
    return budget, threshold
