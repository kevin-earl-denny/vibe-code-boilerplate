"""Configuration management for .vibe/config.json."""

import copy
import json
from pathlib import Path
from typing import Any

from lib.vibe.config_schema import (
    CURRENT_VERSION,
    get_config_version,
    migrate_config,
)
from lib.vibe.utils.file_lock import atomic_write_json, file_lock

CONFIG_PATH = Path(".vibe/config.json")

DEFAULT_CONFIG: dict[str, Any] = {
    "version": "1.0.0",
    "project": {"name": "", "repository": ""},
    "tracker": {"type": None, "config": {"deployed_state": "Deployed"}},
    "github": {"auth_method": None, "owner": "", "repo": ""},
    "branching": {
        "pattern": "{PROJ}-{num}",
        "main_branch": "main",
        "always_rebase": True,
    },
    "worktrees": {
        "location": "sibling",
        "base_path": "../{repo}-worktrees",
        "auto_cleanup": True,
    },
    "labels": {
        "type": ["Bug", "Feature", "Chore", "Refactor"],
        "risk": ["Low Risk", "Medium Risk", "High Risk"],
        "area": ["Frontend", "Backend", "Infra", "Docs"],
        "special": ["HUMAN", "Milestone", "Blocked"],
    },
    "security": {
        "secret_scanner": "gitleaks",
        "sbom_generator": "syft",
        "dependency_scanning": True,
    },
    "secrets": {"providers": [], "allowlist_path": ".vibe/secrets.allowlist.json"},
    "figma": {
        "enabled": False,
        "api_token_env": "FIGMA_API_TOKEN",
    },
    "frontend": {
        "framework": None,
        "ui_library": None,
        "components_path": "src/components",
        "design_tokens_path": None,
    },
    "cost_tracking": {
        "enabled": False,
        "budget_monthly": 0,
        "alert_threshold_pct": 80,
        "providers": {},
    },
}


def get_config_path(base_path: Path | None = None) -> Path:
    """Get the path to the config file."""
    if base_path:
        return base_path / CONFIG_PATH
    return CONFIG_PATH


def config_exists(base_path: Path | None = None) -> bool:
    """Check if config file exists."""
    return get_config_path(base_path).exists()


def load_config(base_path: Path | None = None) -> dict[str, Any]:
    """Load configuration from .vibe/config.json."""
    config_file = get_config_path(base_path)
    if not config_file.exists():
        return copy.deepcopy(DEFAULT_CONFIG)

    with open(config_file) as f:
        config: dict[str, Any] = json.load(f)

    # Auto-migrate if needed
    version = get_config_version(config)
    if version < CURRENT_VERSION:
        config, notes = migrate_config(config)
        if notes:
            save_config(config, base_path)

    return config


def save_config(config: dict[str, Any], base_path: Path | None = None) -> None:
    """Save configuration to .vibe/config.json."""
    config_file = get_config_path(base_path)
    atomic_write_json(config_file, config)


def update_config(updates: dict[str, Any], base_path: Path | None = None) -> dict[str, Any]:
    """Update specific keys in the configuration."""
    config_file = get_config_path(base_path)
    with file_lock(config_file):
        config = load_config(base_path)
        _deep_update(config, updates)
        save_config(config, base_path)
    return config


def _deep_update(base: dict, updates: dict) -> None:
    """Recursively update nested dictionaries."""
    for key, value in updates.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_update(base[key], value)
        else:
            base[key] = value


def get_value(key_path: str, base_path: Path | None = None) -> Any:
    """Get a value from config using dot notation (e.g., 'github.owner')."""
    config = load_config(base_path)
    keys = key_path.split(".")
    value = config
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return None
    return value
