"""Label synchronization between trackers and .vibe/config.json."""

from typing import Any

from lib.vibe.config import load_config, save_config

# Known label patterns for automatic categorization.
# These are matched case-insensitively against tracker label names.
KNOWN_TYPE_LABELS = {"bug", "feature", "chore", "refactor"}
KNOWN_RISK_LABELS = {"low risk", "medium risk", "high risk"}
KNOWN_SPECIAL_LABELS = {"human", "milestone", "blocked"}


def categorize_labels(
    tracker_labels: list[dict[str, str]],
    existing_config_labels: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """Categorize flat tracker labels into config label buckets.

    Labels that match known type/risk/special patterns are placed in those
    buckets. Everything else goes into "area". Existing config labels that
    don't exist in the tracker are preserved (they may be used locally).

    Args:
        tracker_labels: List of dicts with at least a "name" key.
        existing_config_labels: Current labels from config, used to preserve
            local-only labels.

    Returns:
        Dict with keys: type, risk, area, special.
    """
    type_labels: list[str] = []
    risk_labels: list[str] = []
    area_labels: list[str] = []
    special_labels: list[str] = []

    tracker_names = set()
    for label in tracker_labels:
        name = label.get("name", "").strip()
        if not name:
            continue
        tracker_names.add(name)
        lower = name.lower()

        if lower in KNOWN_TYPE_LABELS:
            type_labels.append(name)
        elif lower in KNOWN_RISK_LABELS:
            risk_labels.append(name)
        elif lower in KNOWN_SPECIAL_LABELS:
            special_labels.append(name)
        else:
            area_labels.append(name)

    # Sort each bucket for deterministic output
    type_labels.sort()
    risk_labels.sort()
    area_labels.sort()
    special_labels.sort()

    # Ensure we always have the core type/risk/special labels even if
    # they don't exist in the tracker yet — these are structural to the
    # boilerplate's ticket workflow.
    for default_type in ["Bug", "Chore", "Feature", "Refactor"]:
        if default_type not in type_labels:
            type_labels.append(default_type)
    for default_risk in ["High Risk", "Low Risk", "Medium Risk"]:
        if default_risk not in risk_labels:
            risk_labels.append(default_risk)
    for default_special in ["Blocked", "HUMAN", "Milestone"]:
        if default_special not in special_labels:
            special_labels.append(default_special)

    # Preserve local-only labels from existing config that aren't in the
    # tracker (the user may have added them manually).
    if existing_config_labels:
        for name in existing_config_labels.get("area", []):
            if name not in tracker_names and name not in area_labels:
                area_labels.append(name)
        area_labels.sort()

    # Re-sort after adding defaults
    type_labels.sort()
    risk_labels.sort()
    special_labels.sort()

    return {
        "type": type_labels,
        "risk": risk_labels,
        "area": area_labels,
        "special": special_labels,
    }


def sync_labels_to_config(
    tracker: Any,
    base_path: Any | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Fetch labels from tracker and update config.json.

    Args:
        tracker: A tracker instance with a list_labels() method.
        base_path: Optional base path for config file.
        dry_run: If True, return what would change without saving.

    Returns:
        Dict with keys:
            - "labels": the new label config
            - "tracker_count": number of labels fetched from tracker
            - "changed": whether the config was actually modified
    """
    if not hasattr(tracker, "list_labels"):
        raise NotImplementedError(
            f"Label syncing is not supported by the {tracker.name} tracker."
        )

    tracker_labels = tracker.list_labels()
    config = load_config(base_path)
    existing_labels = config.get("labels", {})

    new_labels = categorize_labels(tracker_labels, existing_labels)

    changed = new_labels != existing_labels

    if changed and not dry_run:
        config["labels"] = new_labels
        save_config(config, base_path)

    return {
        "labels": new_labels,
        "tracker_count": len(tracker_labels),
        "changed": changed,
    }
