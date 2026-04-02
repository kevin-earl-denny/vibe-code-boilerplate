"""Configuration schema validation and migration."""

from typing import Any

# Config schema version
CURRENT_VERSION = 2

# Schema definition for validation
CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "version": {"type": ["string", "integer"]},
        "project": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "repository": {"type": "string"},
            },
        },
        "tracker": {
            "type": "object",
            "properties": {
                "type": {"type": ["string", "null"], "enum": ["linear", "shortcut", None]},
                "config": {"type": "object"},
            },
        },
        "github": {
            "type": "object",
            "properties": {
                "auth_method": {"type": ["string", "null"]},
                "owner": {"type": "string"},
                "repo": {"type": "string"},
            },
        },
        "branching": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "main_branch": {"type": "string"},
                "always_rebase": {"type": "boolean"},
            },
        },
        "worktrees": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "base_path": {"type": "string"},
                "auto_cleanup": {"type": "boolean"},
            },
        },
        "labels": {"type": "object"},
        "security": {"type": "object"},
        "secrets": {"type": "object"},
    },
}

# Known top-level keys (for typo detection)
KNOWN_KEYS = {
    "version",
    "project",
    "tracker",
    "github",
    "branching",
    "worktrees",
    "labels",
    "security",
    "secrets",
    "figma",
    "frontend",
    "database",
    "deployment",
    "observability",
    "testing",
    "boilerplate",
    "views",
}


def validate_config(config: dict[str, Any]) -> list[str]:
    """Validate config against schema. Returns list of error messages."""
    errors: list[str] = []

    # Check for unknown top-level keys (possible typos)
    for key in config:
        if key not in KNOWN_KEYS:
            # Find closest match for typo suggestion
            suggestion = _find_closest(key, KNOWN_KEYS)
            msg = f"Unknown config key: '{key}'"
            if suggestion:
                msg += f" (did you mean '{suggestion}'?)"
            errors.append(msg)

    # Validate tracker type
    tracker = config.get("tracker", {})
    tracker_type = tracker.get("type")
    if tracker_type is not None and tracker_type not in ("linear", "shortcut"):
        errors.append(
            f"Invalid tracker type: '{tracker_type}'. Must be 'linear', 'shortcut', or null."
        )

    # Validate github config
    github = config.get("github", {})
    if github.get("auth_method") and not github.get("owner"):
        errors.append("GitHub auth_method is set but github.owner is missing.")
    if github.get("auth_method") and not github.get("repo"):
        errors.append("GitHub auth_method is set but github.repo is missing.")

    # Validate branching
    branching = config.get("branching", {})
    if "always_rebase" in branching and not isinstance(branching["always_rebase"], bool):
        errors.append("branching.always_rebase must be a boolean.")

    return errors


def get_config_version(config: dict[str, Any]) -> int:
    """Get the config version number."""
    version = config.get("version", "1.0.0")
    if isinstance(version, int):
        return version
    if isinstance(version, str):
        # Parse "1.0.0" -> 1, or "2" -> 2
        try:
            return int(version.split(".")[0])
        except (ValueError, IndexError):
            return 1
    return 1


def migrate_config(config: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Migrate config to the current version. Returns (migrated_config, migration_notes)."""
    notes: list[str] = []
    version = get_config_version(config)

    if version >= CURRENT_VERSION:
        return config, notes

    # Migration v1 -> v2: Add version field as integer
    if version < 2:
        config["version"] = CURRENT_VERSION
        notes.append("Migrated config to version 2 (added integer version field)")

        # Ensure all standard sections exist
        defaults = {
            "worktrees": {
                "location": "sibling",
                "base_path": "../{repo}-worktrees",
                "auto_cleanup": True,
            },
        }
        for key, default_value in defaults.items():
            if key not in config:
                config[key] = default_value
                notes.append(f"Added missing section: {key}")

        # Ensure risk labels exist (added in v2)
        labels = config.get("labels", {})
        if "risk" not in labels:
            labels["risk"] = ["Low Risk", "Medium Risk", "High Risk"]
            config["labels"] = labels
            notes.append("Added missing labels.risk category")

    return config, notes


def _find_closest(key: str, known_keys: set[str]) -> str | None:
    """Find the closest matching known key (simple edit distance)."""
    best_match = None
    best_distance = 3  # Max distance to suggest

    for known in known_keys:
        distance = _edit_distance(key.lower(), known.lower())
        if distance < best_distance:
            best_distance = distance
            best_match = known

    return best_match


def _edit_distance(s1: str, s2: str) -> int:
    """Simple Levenshtein edit distance."""
    if len(s1) < len(s2):
        return _edit_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row

    return prev_row[-1]
