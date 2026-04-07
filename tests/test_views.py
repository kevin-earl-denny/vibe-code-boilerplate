"""Tests for Linear custom views and unblocked filtering."""

from unittest.mock import patch

import pytest
import requests

from lib.vibe.trackers.linear import LinearTracker


class TestListViews:
    """Tests for list_views method."""

    def test_list_views_success(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_response = {
            "data": {
                "customViews": {
                    "nodes": [
                        {
                            "id": "view-1",
                            "name": "Active",
                            "filterData": {"state": {"name": {"in": ["In Progress", "In Review"]}}},
                            "owner": {"name": "Kevin"},
                        },
                        {
                            "id": "view-2",
                            "name": "Backlog",
                            "filterData": {"state": {"name": {"eq": "Backlog"}}},
                            "owner": {"name": "Kevin"},
                        },
                    ]
                }
            }
        }

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            views = tracker.list_views()

        assert len(views) == 2
        assert views[0]["name"] == "Active"
        assert views[0]["owner"] == "Kevin"
        assert views[0]["filterData"] == {"state": {"name": {"in": ["In Progress", "In Review"]}}}
        assert views[1]["name"] == "Backlog"

    def test_list_views_empty(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_response = {"data": {"customViews": {"nodes": []}}}

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            views = tracker.list_views()

        assert views == []

    def test_list_views_api_error(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")

        with patch.object(
            tracker, "_execute_query", side_effect=requests.RequestException("API error")
        ):
            with pytest.raises(RuntimeError, match="Failed to fetch custom views"):
                tracker.list_views()

    def test_list_views_cached(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_response = {
            "data": {
                "customViews": {
                    "nodes": [
                        {
                            "id": "view-1",
                            "name": "Active",
                            "filterData": {},
                            "owner": {"name": "Kevin"},
                        }
                    ]
                }
            }
        }

        with patch.object(tracker, "_execute_query", return_value=mock_response) as mock_query:
            with patch("lib.vibe.trackers.linear.get_cache") as mock_cache_fn:
                cache = mock_cache_fn.return_value
                # First call: cache miss
                cache.get.return_value = None
                views1 = tracker.list_views()
                assert mock_query.call_count == 1
                cache.set.assert_called_once()

                # Second call: cache hit
                cache.get.return_value = views1
                views2 = tracker.list_views()
                assert mock_query.call_count == 1  # No additional API call
                assert views2 == views1

    def test_list_views_owner_missing(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_response = {
            "data": {
                "customViews": {
                    "nodes": [
                        {
                            "id": "view-1",
                            "name": "Shared View",
                            "filterData": {},
                            "owner": None,
                        }
                    ]
                }
            }
        }

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            views = tracker.list_views()

        assert views[0]["owner"] == ""


class TestGetViewFilter:
    """Tests for _get_view_filter method."""

    def test_get_view_filter_found(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_views = [
            {
                "name": "Active",
                "filterData": {"state": {"name": {"eq": "In Progress"}}},
                "owner": "Kevin",
            },
        ]

        with patch.object(tracker, "list_views", return_value=mock_views):
            result = tracker._get_view_filter("Active")

        assert result == {"state": {"name": {"eq": "In Progress"}}}

    def test_get_view_filter_case_insensitive(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_views = [
            {
                "name": "Active",
                "filterData": {"state": {"name": {"eq": "In Progress"}}},
                "owner": "Kevin",
            },
        ]

        with patch.object(tracker, "list_views", return_value=mock_views):
            result = tracker._get_view_filter("active")

        assert result == {"state": {"name": {"eq": "In Progress"}}}

    def test_get_view_filter_not_found(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_views = [
            {"name": "Active", "filterData": {}, "owner": "Kevin"},
            {"name": "Backlog", "filterData": {}, "owner": "Kevin"},
        ]

        with patch.object(tracker, "list_views", return_value=mock_views):
            with pytest.raises(RuntimeError, match="not found.*Available views: Active, Backlog"):
                tracker._get_view_filter("Nonexistent")

    def test_get_view_filter_ambiguous(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_views = [
            {"name": "Active", "filterData": {}, "owner": "Kevin"},
            {"name": "Active", "filterData": {}, "owner": "Jane"},
        ]

        with patch.object(tracker, "list_views", return_value=mock_views):
            with pytest.raises(RuntimeError, match="Multiple views match"):
                tracker._get_view_filter("Active")

    def test_get_view_filter_returns_copy(self) -> None:
        """Ensure modifying the returned filter doesn't affect cached data."""
        tracker = LinearTracker(api_key="test-fake-key")
        original_filter = {"state": {"name": {"eq": "In Progress"}}}
        mock_views = [
            {"name": "Active", "filterData": original_filter, "owner": "Kevin"},
        ]

        with patch.object(tracker, "list_views", return_value=mock_views):
            result = tracker._get_view_filter("Active")
            result["team"] = {"id": {"eq": "team-1"}}

        # Original should be unmodified
        assert "team" not in original_filter


class TestIsBlocked:
    """Tests for _is_blocked static method."""

    def test_not_blocked_no_relations(self) -> None:
        issue = {"inverseRelations": {"nodes": []}}
        assert LinearTracker._is_blocked(issue) is False

    def test_not_blocked_no_inverse_key(self) -> None:
        issue = {}
        assert LinearTracker._is_blocked(issue) is False

    def test_blocked_by_blocks_relation(self) -> None:
        issue = {"inverseRelations": {"nodes": [{"type": "blocks"}]}}
        assert LinearTracker._is_blocked(issue) is True

    def test_not_blocked_by_related_relation(self) -> None:
        issue = {"inverseRelations": {"nodes": [{"type": "related"}]}}
        assert LinearTracker._is_blocked(issue) is False

    def test_blocked_mixed_relations(self) -> None:
        issue = {
            "inverseRelations": {
                "nodes": [
                    {"type": "related"},
                    {"type": "blocks"},
                ]
            }
        }
        assert LinearTracker._is_blocked(issue) is True


class TestListTicketsWithView:
    """Tests for list_tickets with --view flag."""

    def test_list_tickets_applies_view_filter(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        view_filter = {"state": {"name": {"in": ["In Progress", "In Review"]}}}

        mock_response = {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "uuid-1",
                            "identifier": "TEST-1",
                            "title": "Issue 1",
                            "description": "",
                            "state": {"name": "In Progress"},
                            "labels": {"nodes": []},
                            "url": "https://linear.app/test/issue/TEST-1",
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        with (
            patch.object(tracker, "_get_view_filter", return_value=view_filter) as mock_view,
            patch.object(tracker, "_execute_query", return_value=mock_response) as mock_query,
        ):
            tickets = tracker.list_tickets(view="Active")

        mock_view.assert_called_once_with("Active")
        # View filter should be in the query variables
        call_args = mock_query.call_args
        variables = call_args[0][1]
        assert variables["filter"]["state"] == {"name": {"in": ["In Progress", "In Review"]}}
        assert len(tickets) == 1

    def test_list_tickets_view_with_explicit_override(self) -> None:
        """Explicit CLI filters should override view filters."""
        tracker = LinearTracker(api_key="test-fake-key")
        view_filter = {"state": {"name": {"in": ["In Progress", "In Review"]}}}

        mock_response = {
            "data": {
                "issues": {
                    "nodes": [],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        with (
            patch.object(tracker, "_get_view_filter", return_value=view_filter),
            patch.object(tracker, "_execute_query", return_value=mock_response) as mock_query,
        ):
            tracker.list_tickets(view="Active", status="Todo")

        call_args = mock_query.call_args
        variables = call_args[0][1]
        # Explicit --status should override the view's state filter
        assert variables["filter"]["state"] == {"name": {"eq": "Todo"}}

    def test_list_tickets_view_with_team_always_set(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key", team_id="team-123")
        view_filter = {"state": {"name": {"eq": "Backlog"}}}

        mock_response = {
            "data": {
                "issues": {
                    "nodes": [],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        with (
            patch.object(tracker, "_get_view_filter", return_value=view_filter),
            patch.object(tracker, "_execute_query", return_value=mock_response) as mock_query,
        ):
            tracker.list_tickets(view="Backlog")

        call_args = mock_query.call_args
        variables = call_args[0][1]
        assert variables["filter"]["team"] == {"id": {"eq": "team-123"}}


class TestListTicketsUnblocked:
    """Tests for list_tickets with --unblocked flag."""

    def test_unblocked_filters_blocked_tickets(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_response = {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "uuid-1",
                            "identifier": "TEST-1",
                            "title": "Unblocked Issue",
                            "description": "",
                            "state": {"name": "Todo"},
                            "labels": {"nodes": []},
                            "url": "https://linear.app/test/issue/TEST-1",
                            "inverseRelations": {"nodes": []},
                        },
                        {
                            "id": "uuid-2",
                            "identifier": "TEST-2",
                            "title": "Blocked Issue",
                            "description": "",
                            "state": {"name": "Todo"},
                            "labels": {"nodes": []},
                            "url": "https://linear.app/test/issue/TEST-2",
                            "inverseRelations": {"nodes": [{"type": "blocks"}]},
                        },
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            tickets = tracker.list_tickets(unblocked=True)

        assert len(tickets) == 1
        assert tickets[0].id == "TEST-1"

    def test_unblocked_includes_query_fragment(self) -> None:
        """When unblocked=True, the query should include inverseRelations."""
        tracker = LinearTracker(api_key="test-fake-key")
        mock_response = {
            "data": {
                "issues": {
                    "nodes": [],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        with patch.object(tracker, "_execute_query", return_value=mock_response) as mock_query:
            tracker.list_tickets(unblocked=True)

        query = mock_query.call_args[0][0]
        assert "inverseRelations" in query

    def test_query_always_includes_inverse_relations(self) -> None:
        """inverseRelations is always included for blocking relationship display."""
        tracker = LinearTracker(api_key="test-fake-key")
        mock_response = {
            "data": {
                "issues": {
                    "nodes": [],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        with patch.object(tracker, "_execute_query", return_value=mock_response) as mock_query:
            tracker.list_tickets(unblocked=False)

        query = mock_query.call_args[0][0]
        assert "inverseRelations" in query

    def test_unblocked_combined_with_view(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        view_filter = {"state": {"name": {"eq": "Backlog"}}}

        mock_response = {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "uuid-1",
                            "identifier": "TEST-1",
                            "title": "Unblocked Backlog",
                            "description": "",
                            "state": {"name": "Backlog"},
                            "labels": {"nodes": []},
                            "url": "https://linear.app/test/issue/TEST-1",
                            "inverseRelations": {"nodes": []},
                        },
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        with (
            patch.object(tracker, "_get_view_filter", return_value=view_filter),
            patch.object(tracker, "_execute_query", return_value=mock_response) as mock_query,
        ):
            tickets = tracker.list_tickets(view="Backlog", unblocked=True)

        call_args = mock_query.call_args
        variables = call_args[0][1]
        assert variables["filter"]["state"] == {"name": {"eq": "Backlog"}}
        query = mock_query.call_args[0][0]
        assert "inverseRelations" in query
        assert len(tickets) == 1
