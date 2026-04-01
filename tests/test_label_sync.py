"""Tests for label synchronization between trackers and config."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from lib.vibe.label_sync import categorize_labels, sync_labels_to_config


class TestCategorizeLabels:
    """Tests for categorize_labels function."""

    def test_categorize_type_labels(self) -> None:
        labels = [
            {"name": "Bug", "id": "1"},
            {"name": "Feature", "id": "2"},
            {"name": "Chore", "id": "3"},
            {"name": "Refactor", "id": "4"},
        ]
        result = categorize_labels(labels)
        assert result["type"] == ["Bug", "Chore", "Feature", "Refactor"]

    def test_categorize_risk_labels(self) -> None:
        labels = [
            {"name": "Low Risk", "id": "1"},
            {"name": "Medium Risk", "id": "2"},
            {"name": "High Risk", "id": "3"},
        ]
        result = categorize_labels(labels)
        assert result["risk"] == ["High Risk", "Low Risk", "Medium Risk"]

    def test_categorize_special_labels(self) -> None:
        labels = [
            {"name": "HUMAN", "id": "1"},
            {"name": "Milestone", "id": "2"},
            {"name": "Blocked", "id": "3"},
        ]
        result = categorize_labels(labels)
        assert result["special"] == ["Blocked", "HUMAN", "Milestone"]

    def test_unknown_labels_go_to_area(self) -> None:
        labels = [
            {"name": "Data Engineering", "id": "1"},
            {"name": "Frontend", "id": "2"},
            {"name": "Platform", "id": "3"},
        ]
        result = categorize_labels(labels)
        assert result["area"] == ["Data Engineering", "Frontend", "Platform"]

    def test_mixed_labels(self) -> None:
        labels = [
            {"name": "Bug", "id": "1"},
            {"name": "Low Risk", "id": "2"},
            {"name": "Frontend", "id": "3"},
            {"name": "HUMAN", "id": "4"},
            {"name": "Data Engineering", "id": "5"},
        ]
        result = categorize_labels(labels)
        assert "Bug" in result["type"]
        assert "Low Risk" in result["risk"]
        assert "Frontend" in result["area"]
        assert "Data Engineering" in result["area"]
        assert "HUMAN" in result["special"]

    def test_case_insensitive_matching(self) -> None:
        labels = [
            {"name": "bug", "id": "1"},
            {"name": "low risk", "id": "2"},
            {"name": "human", "id": "3"},
        ]
        result = categorize_labels(labels)
        assert "bug" in result["type"]
        assert "low risk" in result["risk"]
        assert "human" in result["special"]

    def test_defaults_always_present(self) -> None:
        """Core type/risk/special labels are always included even if not in tracker."""
        result = categorize_labels([])
        assert "Bug" in result["type"]
        assert "Feature" in result["type"]
        assert "Low Risk" in result["risk"]
        assert "High Risk" in result["risk"]
        assert "HUMAN" in result["special"]
        assert "Milestone" in result["special"]
        assert result["area"] == []

    def test_no_duplicates_when_tracker_has_defaults(self) -> None:
        """If tracker already has Bug, don't add it twice."""
        labels = [{"name": "Bug", "id": "1"}]
        result = categorize_labels(labels)
        assert result["type"].count("Bug") == 1

    def test_preserves_local_only_area_labels(self) -> None:
        """Local-only area labels in existing config are preserved."""
        tracker_labels = [
            {"name": "Frontend", "id": "1"},
            {"name": "Backend", "id": "2"},
        ]
        existing = {
            "type": [],
            "risk": [],
            "area": ["Frontend", "Internal Tools", "Manual Testing"],
            "special": [],
        }
        result = categorize_labels(tracker_labels, existing)
        assert "Frontend" in result["area"]
        assert "Backend" in result["area"]
        assert "Internal Tools" in result["area"]
        assert "Manual Testing" in result["area"]

    def test_no_duplicate_preserved_labels(self) -> None:
        """Labels already in tracker are not duplicated from existing config."""
        tracker_labels = [{"name": "Frontend", "id": "1"}]
        existing = {"area": ["Frontend"]}
        result = categorize_labels(tracker_labels, existing)
        assert result["area"].count("Frontend") == 1

    def test_empty_names_skipped(self) -> None:
        labels = [{"name": "", "id": "1"}, {"name": "  ", "id": "2"}]
        result = categorize_labels(labels)
        assert result["area"] == []

    def test_labels_sorted(self) -> None:
        labels = [
            {"name": "Zebra", "id": "1"},
            {"name": "Alpha", "id": "2"},
            {"name": "Middle", "id": "3"},
        ]
        result = categorize_labels(labels)
        assert result["area"] == ["Alpha", "Middle", "Zebra"]


class TestSyncLabelsToConfig:
    """Tests for sync_labels_to_config function."""

    def test_sync_updates_config(self, tmp_path) -> None:
        config_dir = tmp_path / ".vibe"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "version": "1.0.0",
                    "tracker": {"type": "linear", "config": {}},
                    "labels": {
                        "type": ["Bug", "Feature", "Chore", "Refactor"],
                        "risk": ["Low Risk", "Medium Risk", "High Risk"],
                        "area": ["Frontend", "Backend", "Infra", "Docs"],
                        "special": ["HUMAN", "Milestone", "Blocked"],
                    },
                }
            )
        )

        mock_tracker = MagicMock()
        mock_tracker.name = "linear"
        mock_tracker.list_labels.return_value = [
            {"name": "Bug", "id": "1"},
            {"name": "Feature", "id": "2"},
            {"name": "Data Engineering", "id": "3"},
            {"name": "Platform", "id": "4"},
            {"name": "Low Risk", "id": "5"},
            {"name": "HUMAN", "id": "6"},
        ]

        result = sync_labels_to_config(mock_tracker, base_path=tmp_path)

        assert result["tracker_count"] == 6
        assert result["changed"] is True
        assert "Data Engineering" in result["labels"]["area"]
        assert "Platform" in result["labels"]["area"]

        # Verify config was actually written
        saved = json.loads(config_file.read_text())
        assert "Data Engineering" in saved["labels"]["area"]

    def test_sync_dry_run_does_not_save(self, tmp_path) -> None:
        config_dir = tmp_path / ".vibe"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        original_config = {
            "version": "1.0.0",
            "tracker": {"type": "linear", "config": {}},
            "labels": {
                "type": ["Bug", "Feature", "Chore", "Refactor"],
                "risk": ["Low Risk", "Medium Risk", "High Risk"],
                "area": ["Frontend", "Backend", "Infra", "Docs"],
                "special": ["HUMAN", "Milestone", "Blocked"],
            },
        }
        config_file.write_text(json.dumps(original_config))

        mock_tracker = MagicMock()
        mock_tracker.name = "linear"
        mock_tracker.list_labels.return_value = [
            {"name": "Bug", "id": "1"},
            {"name": "New Area", "id": "2"},
        ]

        result = sync_labels_to_config(mock_tracker, base_path=tmp_path, dry_run=True)

        assert result["changed"] is True
        # Config should NOT be modified
        saved = json.loads(config_file.read_text())
        assert saved["labels"]["area"] == ["Frontend", "Backend", "Infra", "Docs"]

    def test_sync_no_change(self, tmp_path) -> None:
        config_dir = tmp_path / ".vibe"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "version": "1.0.0",
                    "tracker": {"type": "linear", "config": {}},
                    "labels": {
                        "type": ["Bug", "Chore", "Feature", "Refactor"],
                        "risk": ["High Risk", "Low Risk", "Medium Risk"],
                        "area": [],
                        "special": ["Blocked", "HUMAN", "Milestone"],
                    },
                }
            )
        )

        mock_tracker = MagicMock()
        mock_tracker.name = "linear"
        mock_tracker.list_labels.return_value = [
            {"name": "Bug", "id": "1"},
            {"name": "Feature", "id": "2"},
        ]

        result = sync_labels_to_config(mock_tracker, base_path=tmp_path)
        assert result["changed"] is False

    def test_sync_unsupported_tracker(self) -> None:
        mock_tracker = MagicMock(spec=[])  # No list_labels
        mock_tracker.name = "custom"

        with pytest.raises(NotImplementedError, match="not supported"):
            sync_labels_to_config(mock_tracker)


class TestSyncLabelsCommand:
    """Tests for the bin/vibe sync-labels CLI command."""

    CONFIG_WITH_DEFAULTS = {
        "tracker": {"type": "linear", "config": {"team_id": "team1"}},
        "labels": {
            "type": ["Bug", "Feature", "Chore", "Refactor"],
            "risk": ["Low Risk", "Medium Risk", "High Risk"],
            "area": ["Frontend", "Backend", "Infra", "Docs"],
            "special": ["HUMAN", "Milestone", "Blocked"],
        },
    }

    def test_sync_labels_command_success(self) -> None:
        from lib.vibe.cli.main import main

        mock_tracker = MagicMock()
        mock_tracker.list_labels.return_value = [
            {"name": "Bug", "id": "1"},
            {"name": "Data Eng", "id": "2"},
        ]

        runner = CliRunner()
        with patch("lib.vibe.config.load_config", return_value=self.CONFIG_WITH_DEFAULTS.copy()), \
             patch("lib.vibe.trackers.linear.LinearTracker", return_value=mock_tracker), \
             patch("lib.vibe.label_sync.load_config", return_value=self.CONFIG_WITH_DEFAULTS.copy()), \
             patch("lib.vibe.label_sync.save_config"), \
             patch.dict("os.environ", {"LINEAR_API_KEY": "test-key"}):
            result = runner.invoke(main, ["sync-labels"])

        assert result.exit_code == 0
        assert "Fetched 2 labels" in result.output

    def test_sync_labels_linear_no_api_key(self) -> None:
        from lib.vibe.cli.main import main

        runner = CliRunner()
        with patch("lib.vibe.config.load_config", return_value={
            "tracker": {"type": "linear", "config": {"team_id": "t1"}},
        }), patch.dict("os.environ", {}, clear=False):
            # Ensure LINEAR_API_KEY is not set
            os.environ.pop("LINEAR_API_KEY", None)
            result = runner.invoke(main, ["sync-labels"])

        assert result.exit_code == 1
        assert "LINEAR_API_KEY" in result.output

    def test_sync_labels_no_tracker(self) -> None:
        from lib.vibe.cli.main import main

        runner = CliRunner()
        with patch("lib.vibe.config.load_config", return_value={"tracker": {"type": None, "config": {}}}):
            result = runner.invoke(main, ["sync-labels"])

        assert result.exit_code == 1
        assert "No tracker configured" in result.output

    def test_sync_labels_dry_run(self) -> None:
        from lib.vibe.cli.main import main

        mock_tracker = MagicMock()
        mock_tracker.list_labels.return_value = [
            {"name": "Bug", "id": "1"},
            {"name": "Custom Area", "id": "2"},
        ]

        runner = CliRunner()
        with patch("lib.vibe.config.load_config", return_value=self.CONFIG_WITH_DEFAULTS.copy()), \
             patch("lib.vibe.trackers.linear.LinearTracker", return_value=mock_tracker), \
             patch("lib.vibe.label_sync.load_config", return_value=self.CONFIG_WITH_DEFAULTS.copy()), \
             patch("lib.vibe.label_sync.save_config") as mock_save, \
             patch.dict("os.environ", {"LINEAR_API_KEY": "test-key"}):
            result = runner.invoke(main, ["sync-labels", "--dry-run"])

        assert result.exit_code == 0
        assert "dry run" in result.output.lower()
        mock_save.assert_not_called()

    def test_sync_labels_json_output(self) -> None:
        from lib.vibe.cli.main import main

        mock_tracker = MagicMock()
        mock_tracker.list_labels.return_value = [{"name": "Bug", "id": "1"}]

        runner = CliRunner()
        with patch("lib.vibe.config.load_config", return_value={"tracker": {"type": "linear", "config": {"team_id": "t1"}}, "labels": {}}), \
             patch("lib.vibe.trackers.linear.LinearTracker", return_value=mock_tracker), \
             patch("lib.vibe.label_sync.load_config", return_value={"tracker": {"type": "linear", "config": {}}, "labels": {}}), \
             patch("lib.vibe.label_sync.save_config"), \
             patch.dict("os.environ", {"LINEAR_API_KEY": "test-key"}):
            result = runner.invoke(main, ["sync-labels", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "labels" in output
        assert "type" in output["labels"]
        assert "area" in output["labels"]
        assert "tracker_count" in output
        assert "changed" in output


class TestDoctorLabelCheck:
    """Tests for the doctor label sync check."""

    def test_check_warns_on_default_labels(self) -> None:
        from lib.vibe.doctor import Status, check_label_sync

        config = {
            "tracker": {"type": "linear"},
            "labels": {
                "type": ["Bug", "Feature", "Chore", "Refactor"],
                "risk": ["Low Risk", "Medium Risk", "High Risk"],
                "area": ["Frontend", "Backend", "Infra", "Docs"],
                "special": ["HUMAN", "Milestone", "Blocked"],
            },
        }
        result = check_label_sync(config)
        assert result.status == Status.WARN
        assert "sync-labels" in result.fix_hint

    def test_check_passes_when_area_differs_from_defaults(self) -> None:
        from lib.vibe.doctor import Status, check_label_sync

        config = {
            "tracker": {"type": "linear"},
            "labels": {
                "type": ["Bug", "Feature", "Chore", "Refactor"],
                "risk": ["Low Risk", "Medium Risk", "High Risk"],
                "area": ["Data Engineering", "Platform", "Frontend"],
                "special": ["HUMAN", "Milestone", "Blocked"],
            },
        }
        result = check_label_sync(config)
        assert result.status == Status.PASS
        assert "differ from defaults" in result.message

    def test_check_skips_without_tracker(self) -> None:
        from lib.vibe.doctor import Status, check_label_sync

        config = {"tracker": {"type": None}, "labels": {}}
        result = check_label_sync(config)
        assert result.status == Status.SKIP
