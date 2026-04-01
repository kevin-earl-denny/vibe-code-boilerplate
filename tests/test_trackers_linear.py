"""Tests for Linear tracker integration."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from lib.vibe.trackers.linear import LINEAR_API_URL, LinearTracker


class TestLinearTrackerInit:
    """Tests for LinearTracker initialization."""

    def test_init_with_api_key(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key-not-real")
        assert tracker._api_key == "test-fake-key-not-real"
        assert tracker._headers["Authorization"] == "test-fake-key-not-real"
        assert tracker._headers["Content-Type"] == "application/json"

    def test_init_with_team_id(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key", team_id="team_abc")
        assert tracker._team_id == "team_abc"

    def test_init_from_env(self) -> None:
        with patch.dict("os.environ", {"LINEAR_API_KEY": "test-key-from-env"}):
            tracker = LinearTracker()
        assert tracker._api_key == "test-key-from-env"

    def test_init_no_key_empty_headers(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            tracker = LinearTracker()
        assert tracker._api_key is None
        assert tracker._headers == {}


class TestLinearTrackerName:
    """Tests for name property."""

    def test_name_returns_linear(self) -> None:
        tracker = LinearTracker()
        assert tracker.name == "linear"


class TestLinearTrackerAuthenticate:
    """Tests for authenticate method."""

    def test_authenticate_success(self) -> None:
        tracker = LinearTracker()
        mock_response = {"data": {"viewer": {"id": "user123", "name": "Test User"}}}

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            result = tracker.authenticate(api_key="test-valid-key")

        assert result is True
        assert tracker._api_key == "test-valid-key"

    def test_authenticate_failure_no_viewer(self) -> None:
        tracker = LinearTracker()
        mock_response = {"data": {}}

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            result = tracker.authenticate(api_key="test-invalid-key")  # noqa: S106

        assert result is False

    def test_authenticate_failure_exception(self) -> None:
        tracker = LinearTracker()

        with patch.object(
            tracker, "_execute_query", side_effect=requests.RequestException("API error")
        ):
            result = tracker.authenticate(api_key="test-error-key")  # noqa: S106

        assert result is False

    def test_authenticate_no_api_key(self) -> None:
        tracker = LinearTracker()
        result = tracker.authenticate()
        assert result is False


class TestLinearTrackerExecuteQuery:
    """Tests for _execute_query method."""

    def test_execute_query_success(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"viewer": {"id": "123"}}}
        mock_response.raise_for_status = MagicMock()

        with patch(
            "lib.vibe.trackers.linear.requests.post", return_value=mock_response
        ) as mock_post:
            result = tracker._execute_query("query { viewer { id } }")

        mock_post.assert_called_once_with(
            LINEAR_API_URL,
            headers=tracker._headers,
            json={"query": "query { viewer { id } }"},
            timeout=30,
        )
        assert result == {"data": {"viewer": {"id": "123"}}}

    def test_execute_query_with_variables(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"issue": {"id": "abc"}}}
        mock_response.raise_for_status = MagicMock()

        with patch(
            "lib.vibe.trackers.linear.requests.post", return_value=mock_response
        ) as mock_post:
            _result = tracker._execute_query(
                "query GetIssue($id: String!) { issue(id: $id) { id } }", {"id": "TEST-1"}
            )

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]["json"]["variables"] == {"id": "TEST-1"}


class TestLinearTrackerGetTicket:
    """Tests for get_ticket method."""

    def test_get_ticket_success(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_issue = {
            "id": "uuid-123",
            "identifier": "TEST-1",
            "title": "Test Issue",
            "description": "Description here",
            "state": {"id": "state1", "name": "Todo"},
            "team": {"id": "team123"},
            "labels": {"nodes": [{"name": "Bug"}, {"name": "High Risk"}]},
            "url": "https://linear.app/test/issue/TEST-1",
        }
        mock_response = {"data": {"issue": mock_issue}}

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            ticket = tracker.get_ticket("TEST-1")

        assert ticket is not None
        assert ticket.id == "TEST-1"
        assert ticket.title == "Test Issue"
        assert ticket.description == "Description here"
        assert ticket.status == "Todo"
        assert ticket.labels == ["Bug", "High Risk"]
        assert ticket.url == "https://linear.app/test/issue/TEST-1"

    def test_get_ticket_not_found(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_response = {"data": {"issue": None}}

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            ticket = tracker.get_ticket("NONEXISTENT-999")

        assert ticket is None

    def test_get_ticket_exception(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")

        with patch.object(
            tracker, "_execute_query", side_effect=requests.RequestException("API error")
        ):
            ticket = tracker.get_ticket("TEST-1")

        assert ticket is None


class TestLinearTrackerListTickets:
    """Tests for list_tickets method."""

    def test_list_tickets_success(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_issues = [
            {
                "id": "uuid-1",
                "identifier": "TEST-1",
                "title": "Issue 1",
                "description": "Desc 1",
                "state": {"name": "Todo"},
                "labels": {"nodes": []},
                "url": "https://linear.app/test/issue/TEST-1",
            },
            {
                "id": "uuid-2",
                "identifier": "TEST-2",
                "title": "Issue 2",
                "description": "Desc 2",
                "state": {"name": "In Progress"},
                "labels": {"nodes": [{"name": "Feature"}]},
                "url": "https://linear.app/test/issue/TEST-2",
            },
        ]
        mock_response = {
            "data": {
                "issues": {
                    "nodes": mock_issues,
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            tickets = tracker.list_tickets()

        assert len(tickets) == 2
        assert tickets[0].id == "TEST-1"
        assert tickets[1].id == "TEST-2"
        assert tickets[1].labels == ["Feature"]

    def test_list_tickets_with_status_filter(self) -> None:
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
            tracker.list_tickets(status="Todo")

        call_args = mock_query.call_args
        variables = call_args[0][1]
        assert variables["filter"]["state"] == {"name": {"eq": "Todo"}}

    def test_list_tickets_with_label_filter(self) -> None:
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
            tracker.list_tickets(labels=["Bug", "Feature"])

        call_args = mock_query.call_args
        variables = call_args[0][1]
        assert variables["filter"]["labels"] == {"name": {"in": ["Bug", "Feature"]}}

    def test_list_tickets_with_team_filter(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key", team_id="team_abc")
        mock_response = {
            "data": {
                "issues": {
                    "nodes": [],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        with patch.object(tracker, "_execute_query", return_value=mock_response) as mock_query:
            tracker.list_tickets()

        call_args = mock_query.call_args
        variables = call_args[0][1]
        assert variables["filter"]["team"] == {"id": {"eq": "team_abc"}}

    def test_list_tickets_with_limit(self) -> None:
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
            tracker.list_tickets(limit=10)

        call_args = mock_query.call_args
        variables = call_args[0][1]
        assert variables["first"] == 10

    def test_list_tickets_paginates_multiple_pages(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        page1_response = {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "uuid-1",
                            "identifier": "TEST-1",
                            "title": "Issue 1",
                            "description": "",
                            "state": {"name": "Todo"},
                            "labels": {"nodes": []},
                            "url": "",
                        },
                    ],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
                }
            }
        }
        page2_response = {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "uuid-2",
                            "identifier": "TEST-2",
                            "title": "Issue 2",
                            "description": "",
                            "state": {"name": "Todo"},
                            "labels": {"nodes": []},
                            "url": "",
                        },
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        with patch.object(
            tracker, "_execute_query", side_effect=[page1_response, page2_response]
        ) as mock_query:
            tickets = tracker.list_tickets(limit=100)

        assert len(tickets) == 2
        assert tickets[0].id == "TEST-1"
        assert tickets[1].id == "TEST-2"
        # Verify second call includes cursor
        second_call_vars = mock_query.call_args_list[1][0][1]
        assert second_call_vars["after"] == "cursor-1"

    def test_list_tickets_stops_at_limit(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        page1_response = {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": f"uuid-{i}",
                            "identifier": f"TEST-{i}",
                            "title": f"Issue {i}",
                            "description": "",
                            "state": {"name": "Todo"},
                            "labels": {"nodes": []},
                            "url": "",
                        }
                        for i in range(3)
                    ],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
                }
            }
        }

        with patch.object(tracker, "_execute_query", return_value=page1_response) as mock_query:
            tickets = tracker.list_tickets(limit=2)

        assert len(tickets) == 2
        # Should only make one API call since we got enough results
        assert mock_query.call_count == 1

    def test_list_tickets_exception_returns_partial(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        page1_response = {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "uuid-1",
                            "identifier": "TEST-1",
                            "title": "Issue 1",
                            "description": "",
                            "state": {"name": "Todo"},
                            "labels": {"nodes": []},
                            "url": "",
                        },
                    ],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
                }
            }
        }

        with patch.object(
            tracker,
            "_execute_query",
            side_effect=[page1_response, requests.RequestException("API error")],
        ):
            tickets = tracker.list_tickets(limit=100)

        # Should return the tickets from page 1
        assert len(tickets) == 1
        assert tickets[0].id == "TEST-1"

    def test_list_tickets_exception_returns_empty(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")

        with patch.object(
            tracker, "_execute_query", side_effect=requests.RequestException("API error")
        ):
            tickets = tracker.list_tickets()

        assert tickets == []


class TestLinearTrackerCreateTicket:
    """Tests for create_ticket method."""

    def test_create_ticket_success(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key", team_id="team_abc")
        mock_issue = {
            "id": "uuid-new",
            "identifier": "TEST-100",
            "title": "New Issue",
            "description": "New description",
            "state": {"name": "Backlog"},
            "labels": {"nodes": []},
            "url": "https://linear.app/test/issue/TEST-100",
        }
        mock_response = {"data": {"issueCreate": {"success": True, "issue": mock_issue}}}

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            ticket = tracker.create_ticket("New Issue", "New description")

        assert ticket.id == "TEST-100"
        assert ticket.title == "New Issue"

    def test_create_ticket_with_labels(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key", team_id="team_abc")
        mock_issue = {
            "id": "uuid-new",
            "identifier": "TEST-101",
            "title": "Labeled Issue",
            "description": "Description",
            "state": {"name": "Backlog"},
            "labels": {"nodes": [{"name": "Bug"}]},
            "url": "https://linear.app/test/issue/TEST-101",
        }
        mock_response = {"data": {"issueCreate": {"success": True, "issue": mock_issue}}}

        with (
            patch.object(tracker, "_execute_query", return_value=mock_response),
            patch.object(tracker, "_get_label_ids", return_value=["label-id-1"]) as mock_labels,
        ):
            ticket = tracker.create_ticket("Labeled Issue", "Description", labels=["Bug"])

        mock_labels.assert_called_once_with("team_abc", ["Bug"])
        assert ticket.labels == ["Bug"]

    def test_create_ticket_failure(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key", team_id="team_abc")
        mock_response = {"data": {"issueCreate": {"success": False, "issue": None}}}

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            with pytest.raises(RuntimeError, match="Failed to create ticket"):
                tracker.create_ticket("Title", "Description")


class TestLinearTrackerUpdateTicket:
    """Tests for update_ticket method."""

    def test_update_ticket_title(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_current_issue = {
            "id": "uuid-1",
            "identifier": "TEST-1",
            "title": "Old Title",
            "description": "Desc",
            "state": {"name": "Todo"},
            "team": {"id": "team_abc"},
            "labels": {"nodes": []},
            "url": "https://linear.app/test/issue/TEST-1",
        }
        mock_updated_issue = {
            "id": "uuid-1",
            "identifier": "TEST-1",
            "title": "Updated Title",
            "description": "Desc",
            "state": {"name": "Todo"},
            "labels": {"nodes": []},
            "url": "https://linear.app/test/issue/TEST-1",
        }
        mock_response = {"data": {"issueUpdate": {"success": True, "issue": mock_updated_issue}}}

        with patch.object(tracker, "get_ticket") as mock_get:
            mock_get.return_value = tracker._parse_issue(mock_current_issue)
            with patch.object(tracker, "_execute_query", return_value=mock_response):
                ticket = tracker.update_ticket("TEST-1", title="Updated Title")

        assert ticket.title == "Updated Title"

    def test_update_ticket_status(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        # First call returns the current ticket, second call is the update
        mock_current_issue = {
            "id": "uuid-1",
            "identifier": "TEST-1",
            "title": "Title",
            "description": "Desc",
            "state": {"id": "state-todo", "name": "Todo"},
            "team": {"id": "team_abc"},
            "labels": {"nodes": []},
            "url": "https://linear.app/test/issue/TEST-1",
        }
        mock_updated_issue = {
            "id": "uuid-1",
            "identifier": "TEST-1",
            "title": "Title",
            "description": "Desc",
            "state": {"name": "Done"},
            "labels": {"nodes": []},
            "url": "https://linear.app/test/issue/TEST-1",
        }

        with patch.object(tracker, "get_ticket") as mock_get:
            mock_get.return_value = tracker._parse_issue(mock_current_issue)
            with patch.object(tracker, "_get_workflow_state_id", return_value="state-done"):
                with patch.object(
                    tracker,
                    "_execute_query",
                    return_value={
                        "data": {"issueUpdate": {"success": True, "issue": mock_updated_issue}}
                    },
                ):
                    ticket = tracker.update_ticket("TEST-1", status="Done")

        assert ticket.status == "Done"

    def test_update_ticket_status_not_found(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")

        with patch.object(tracker, "get_ticket", return_value=None):
            with pytest.raises(RuntimeError, match="Ticket not found"):
                tracker.update_ticket("NONEXISTENT-999", status="Done")

    def test_update_ticket_status_no_team(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_issue = {
            "id": "uuid-1",
            "identifier": "TEST-1",
            "title": "Title",
            "description": "Desc",
            "state": {"name": "Todo"},
            "team": None,
            "labels": {"nodes": []},
            "url": "https://linear.app/test/issue/TEST-1",
        }

        with patch.object(tracker, "get_ticket") as mock_get:
            mock_get.return_value = tracker._parse_issue(mock_issue)
            with pytest.raises(RuntimeError, match="Cannot resolve status: issue has no team"):
                tracker.update_ticket("TEST-1", status="Done")

    def test_update_ticket_status_invalid_state(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_issue = {
            "id": "uuid-1",
            "identifier": "TEST-1",
            "title": "Title",
            "description": "Desc",
            "state": {"name": "Todo"},
            "team": {"id": "team_abc"},
            "labels": {"nodes": []},
            "url": "https://linear.app/test/issue/TEST-1",
        }

        with patch.object(tracker, "get_ticket") as mock_get:
            mock_get.return_value = tracker._parse_issue(mock_issue)
            with patch.object(tracker, "_get_workflow_state_id", return_value=None):
                with pytest.raises(RuntimeError, match="No workflow state named 'InvalidState'"):
                    tracker.update_ticket("TEST-1", status="InvalidState")

    def test_update_ticket_failure(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_current_issue = {
            "id": "uuid-1",
            "identifier": "TEST-1",
            "title": "Title",
            "description": "Desc",
            "state": {"name": "Todo"},
            "team": {"id": "team_abc"},
            "labels": {"nodes": []},
            "url": "https://linear.app/test/issue/TEST-1",
        }
        mock_response = {"data": {"issueUpdate": {"success": False, "issue": None}}}

        with patch.object(tracker, "get_ticket") as mock_get:
            mock_get.return_value = tracker._parse_issue(mock_current_issue)
            with patch.object(tracker, "_execute_query", return_value=mock_response):
                with pytest.raises(RuntimeError, match="Failed to update ticket"):
                    tracker.update_ticket("TEST-1", title="New Title")

    def test_update_ticket_labels(self) -> None:
        """update_ticket with labels resolves identifier to UUID."""
        tracker = LinearTracker(api_key="test-fake-key")
        mock_current_issue = {
            "id": "uuid-1",
            "identifier": "TEST-1",
            "title": "Title",
            "description": "Desc",
            "state": {"name": "Todo"},
            "team": {"id": "team_abc"},
            "labels": {"nodes": []},
            "url": "https://linear.app/test/issue/TEST-1",
        }
        mock_updated_issue = {
            "id": "uuid-1",
            "identifier": "TEST-1",
            "title": "Title",
            "description": "Desc",
            "state": {"name": "Todo"},
            "labels": {"nodes": [{"id": "label-id-1", "name": "Backend"}]},
            "url": "https://linear.app/test/issue/TEST-1",
        }
        mock_response = {"data": {"issueUpdate": {"success": True, "issue": mock_updated_issue}}}

        with patch.object(tracker, "get_ticket") as mock_get:
            mock_get.return_value = tracker._parse_issue(mock_current_issue)
            with patch.object(tracker, "_get_or_create_label_ids", return_value=["label-id-1"]):
                with patch.object(tracker, "_execute_query", return_value=mock_response):
                    ticket = tracker.update_ticket("TEST-1", labels=["Backend"])

        assert "Backend" in ticket.labels

    def test_update_ticket_labels_merges_with_existing(self) -> None:
        """update_ticket with labels should merge new labels with existing ones."""
        tracker = LinearTracker(api_key="test-fake-key")
        mock_current_issue = {
            "id": "uuid-1",
            "identifier": "TEST-1",
            "title": "Title",
            "description": "Desc",
            "state": {"name": "Todo"},
            "team": {"id": "team_abc"},
            "labels": {"nodes": [
                {"id": "existing-label-1", "name": "Feature"},
                {"id": "existing-label-2", "name": "Frontend"},
            ]},
            "url": "https://linear.app/test/issue/TEST-1",
        }
        mock_updated_issue = {
            "id": "uuid-1",
            "identifier": "TEST-1",
            "title": "Title",
            "description": "Desc",
            "state": {"name": "Todo"},
            "labels": {"nodes": [
                {"id": "existing-label-1", "name": "Feature"},
                {"id": "existing-label-2", "name": "Frontend"},
                {"id": "new-label-1", "name": "Backend"},
            ]},
            "url": "https://linear.app/test/issue/TEST-1",
        }
        mock_response = {"data": {"issueUpdate": {"success": True, "issue": mock_updated_issue}}}

        with patch.object(tracker, "get_ticket") as mock_get:
            mock_get.return_value = tracker._parse_issue(mock_current_issue)
            with patch.object(tracker, "_get_or_create_label_ids", return_value=["new-label-1"]) as mock_labels:
                with patch.object(tracker, "_execute_query", return_value=mock_response) as mock_exec:
                    ticket = tracker.update_ticket("TEST-1", labels=["Backend"])

        # Verify the mutation was called with merged label IDs
        call_args = mock_exec.call_args
        input_obj = call_args[0][1]["input"]
        assert set(input_obj["labelIds"]) == {"existing-label-1", "existing-label-2", "new-label-1"}

        # Verify the returned ticket has all labels
        assert "Feature" in ticket.labels
        assert "Frontend" in ticket.labels
        assert "Backend" in ticket.labels

    def test_update_ticket_labels_deduplicates(self) -> None:
        """Adding a label that already exists should not create duplicates."""
        tracker = LinearTracker(api_key="test-fake-key")
        mock_current_issue = {
            "id": "uuid-1",
            "identifier": "TEST-1",
            "title": "Title",
            "description": "Desc",
            "state": {"name": "Todo"},
            "team": {"id": "team_abc"},
            "labels": {"nodes": [{"id": "label-1", "name": "Backend"}]},
            "url": "https://linear.app/test/issue/TEST-1",
        }
        mock_updated_issue = {
            "id": "uuid-1",
            "identifier": "TEST-1",
            "title": "Title",
            "description": "Desc",
            "state": {"name": "Todo"},
            "labels": {"nodes": [{"id": "label-1", "name": "Backend"}]},
            "url": "https://linear.app/test/issue/TEST-1",
        }
        mock_response = {"data": {"issueUpdate": {"success": True, "issue": mock_updated_issue}}}

        with patch.object(tracker, "get_ticket") as mock_get:
            mock_get.return_value = tracker._parse_issue(mock_current_issue)
            with patch.object(tracker, "_get_or_create_label_ids", return_value=["label-1"]):
                with patch.object(tracker, "_execute_query", return_value=mock_response) as mock_exec:
                    tracker.update_ticket("TEST-1", labels=["Backend"])

        # Should only have the one label ID, no duplicates
        call_args = mock_exec.call_args
        input_obj = call_args[0][1]["input"]
        assert input_obj["labelIds"] == ["label-1"]

    def test_update_ticket_uses_uuid_not_identifier(self) -> None:
        """The issueUpdate mutation must receive the UUID, not the identifier."""
        tracker = LinearTracker(api_key="test-fake-key")
        mock_current_issue = {
            "id": "uuid-1",
            "identifier": "TEST-1",
            "title": "Title",
            "description": "Desc",
            "state": {"name": "Todo"},
            "team": {"id": "team_abc"},
            "labels": {"nodes": []},
            "url": "https://linear.app/test/issue/TEST-1",
        }
        mock_updated_issue = {
            "id": "uuid-1",
            "identifier": "TEST-1",
            "title": "New Title",
            "description": "Desc",
            "state": {"name": "Todo"},
            "labels": {"nodes": []},
            "url": "https://linear.app/test/issue/TEST-1",
        }
        mock_response = {"data": {"issueUpdate": {"success": True, "issue": mock_updated_issue}}}

        with patch.object(tracker, "get_ticket") as mock_get:
            mock_get.return_value = tracker._parse_issue(mock_current_issue)
            with patch.object(tracker, "_execute_query", return_value=mock_response) as mock_exec:
                tracker.update_ticket("TEST-1", title="New Title")

        # The mutation should use the UUID ("uuid-1"), not the identifier ("TEST-1")
        call_args = mock_exec.call_args
        variables = call_args[0][1]  # second positional arg is variables
        assert variables["id"] == "uuid-1"


class TestLinearTrackerCommentTicket:
    """Tests for comment_ticket method."""

    def test_comment_ticket_success(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_issue = {
            "id": "uuid-1",
            "identifier": "TEST-1",
            "title": "Title",
            "description": "Desc",
            "state": {"name": "Todo"},
            "labels": {"nodes": []},
            "url": "https://linear.app/test/issue/TEST-1",
        }
        mock_comment_response = {
            "data": {"commentCreate": {"success": True, "comment": {"id": "comment-1"}}}
        }

        with patch.object(tracker, "get_ticket") as mock_get:
            mock_get.return_value = tracker._parse_issue(mock_issue)
            with patch.object(
                tracker, "_execute_query", return_value=mock_comment_response
            ) as mock_query:
                tracker.comment_ticket("TEST-1", "This is a comment")

        # Verify the comment mutation was called
        call_args = mock_query.call_args
        variables = call_args[0][1]
        assert variables["input"]["issueId"] == "uuid-1"
        assert variables["input"]["body"] == "This is a comment"

    def test_comment_ticket_not_found(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")

        with patch.object(tracker, "get_ticket", return_value=None):
            with pytest.raises(RuntimeError, match="Ticket not found"):
                tracker.comment_ticket("NONEXISTENT-999", "Comment")

    def test_comment_ticket_no_issue_id(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_issue = {
            "id": None,
            "identifier": "TEST-1",
            "title": "Title",
            "description": "Desc",
            "state": {"name": "Todo"},
            "labels": {"nodes": []},
            "url": "https://linear.app/test/issue/TEST-1",
        }

        with patch.object(tracker, "get_ticket") as mock_get:
            mock_get.return_value = tracker._parse_issue(mock_issue)
            with pytest.raises(RuntimeError, match="Cannot comment: issue has no id"):
                tracker.comment_ticket("TEST-1", "Comment")


class TestLinearTrackerValidateConfig:
    """Tests for validate_config method."""

    def test_validate_config_valid(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key", team_id="team_abc")

        with patch.object(tracker, "authenticate", return_value=True):
            valid, issues = tracker.validate_config()

        assert valid is True
        assert issues == []

    def test_validate_config_no_api_key(self) -> None:
        tracker = LinearTracker(team_id="team_abc")
        tracker._api_key = None

        valid, issues = tracker.validate_config()

        assert valid is False
        assert "LINEAR_API_KEY not set" in issues

    def test_validate_config_no_team_id(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")

        with patch.object(tracker, "authenticate", return_value=True):
            valid, issues = tracker.validate_config()

        assert valid is False
        assert "Linear team ID not configured" in issues

    def test_validate_config_invalid_key(self) -> None:
        tracker = LinearTracker(api_key="test-invalid-key", team_id="team_abc")

        with patch.object(tracker, "authenticate", return_value=False):
            valid, issues = tracker.validate_config()

        assert valid is False
        assert "LINEAR_API_KEY is invalid or expired" in issues


class TestLinearTrackerGetLabelIds:
    """Tests for _get_label_ids method."""

    def test_get_label_ids_success(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_labels = [
            {"id": "label-1", "name": "Bug"},
            {"id": "label-2", "name": "Feature"},
            {"id": "label-3", "name": "Chore"},
        ]
        mock_response = {"data": {"team": {"labels": {"nodes": mock_labels}}}}

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            label_ids = tracker._get_label_ids("team_abc", ["Bug", "Feature"])

        assert label_ids == ["label-1", "label-2"]

    def test_get_label_ids_partial_match(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_labels = [{"id": "label-1", "name": "Bug"}]
        mock_response = {"data": {"team": {"labels": {"nodes": mock_labels}}}}

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            label_ids = tracker._get_label_ids("team_abc", ["Bug", "NonexistentLabel"])

        assert label_ids == ["label-1"]

    def test_get_label_ids_no_team(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        label_ids = tracker._get_label_ids(None, ["Bug"])
        assert label_ids == []

    def test_get_label_ids_no_labels(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        label_ids = tracker._get_label_ids("team_abc", [])
        assert label_ids == []

    def test_get_label_ids_exception(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")

        # Clear cache to avoid stale data from prior tests
        from lib.vibe.utils.cache import get_cache

        get_cache().invalidate("linear_labels_team_abc")

        with patch.object(
            tracker, "_execute_query", side_effect=requests.RequestException("API error")
        ):
            label_ids = tracker._get_label_ids("team_abc", ["Bug"])

        assert label_ids == []


class TestLinearTrackerGetLabelIdsCaseInsensitive:
    """Tests for case-insensitive label matching in _get_label_ids."""

    def test_get_label_ids_case_insensitive_match(self) -> None:
        """Label 'Backend' in input matches 'backend' in Linear."""
        tracker = LinearTracker(api_key="test-fake-key")
        mock_labels = [
            {"id": "label-1", "name": "backend"},
            {"id": "label-2", "name": "Frontend"},
        ]
        mock_response = {"data": {"team": {"labels": {"nodes": mock_labels}}}}

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            label_ids = tracker._get_label_ids("team_abc", ["Backend"])

        assert label_ids == ["label-1"]

    def test_get_label_ids_uppercase_input(self) -> None:
        """Label 'DATABASE' in input matches 'database' in Linear."""
        tracker = LinearTracker(api_key="test-fake-key")
        mock_labels = [{"id": "label-1", "name": "database"}]
        mock_response = {"data": {"team": {"labels": {"nodes": mock_labels}}}}

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            label_ids = tracker._get_label_ids("team_abc", ["DATABASE"])

        assert label_ids == ["label-1"]

    def test_get_label_ids_mixed_case_multiple(self) -> None:
        """Multiple labels with different casings all resolve correctly."""
        tracker = LinearTracker(api_key="test-fake-key")
        mock_labels = [
            {"id": "label-1", "name": "Bug"},
            {"id": "label-2", "name": "high risk"},
            {"id": "label-3", "name": "BACKEND"},
        ]
        mock_response = {"data": {"team": {"labels": {"nodes": mock_labels}}}}

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            label_ids = tracker._get_label_ids("team_abc", ["bug", "High Risk", "backend"])

        assert label_ids == ["label-1", "label-2", "label-3"]

    def test_get_label_ids_case_insensitive_from_cache(self) -> None:
        """Cached labels also use case-insensitive matching."""
        tracker = LinearTracker(api_key="test-fake-key")
        cached_data = [
            {"name": "backend", "id": "label-1"},
            {"name": "Frontend", "id": "label-2"},
        ]

        with patch("lib.vibe.trackers.linear.get_cache") as mock_get_cache:
            mock_cache = MagicMock()
            mock_cache.get.return_value = cached_data
            mock_get_cache.return_value = mock_cache

            label_ids = tracker._get_label_ids("team_cached", ["BACKEND", "frontend"])

        assert label_ids == ["label-1", "label-2"]


class TestLinearTrackerGetOrCreateLabelIdsCaseInsensitive:
    """Tests for case-insensitive label matching in _get_or_create_label_ids."""

    def test_get_or_create_skips_creation_for_case_mismatch(self) -> None:
        """If 'backend' exists in Linear, passing 'Backend' should match it, not create a new one."""
        tracker = LinearTracker(api_key="test-fake-key")
        mock_labels = [
            {"id": "label-1", "name": "backend"},
            {"id": "label-2", "name": "Feature"},
        ]
        mock_response = {"data": {"team": {"labels": {"nodes": mock_labels}}}}

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            with patch.object(tracker, "_create_label") as mock_create:
                label_ids = tracker._get_or_create_label_ids("team_abc", ["Backend", "Feature"])

        mock_create.assert_not_called()
        assert label_ids == ["label-1", "label-2"]

    def test_get_or_create_creates_genuinely_new_label(self) -> None:
        """A label that truly doesn't exist (even case-insensitively) should be created."""
        tracker = LinearTracker(api_key="test-fake-key")
        mock_labels = [{"id": "label-1", "name": "Bug"}]
        mock_response = {"data": {"team": {"labels": {"nodes": mock_labels}}}}

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            with patch.object(tracker, "_create_label", return_value="new-label-id") as mock_create:
                label_ids = tracker._get_or_create_label_ids("team_abc", ["Bug", "NewLabel"])

        mock_create.assert_called_once_with("team_abc", "NewLabel")
        assert label_ids == ["label-1", "new-label-id"]

    def test_get_or_create_warns_on_failed_creation(self) -> None:
        """A warning is logged when label creation fails."""
        tracker = LinearTracker(api_key="test-fake-key")
        mock_labels = [{"id": "label-1", "name": "Bug"}]
        mock_response = {"data": {"team": {"labels": {"nodes": mock_labels}}}}
        with patch.object(tracker, "_execute_query", return_value=mock_response):
            with patch.object(tracker, "_create_label", return_value=None):
                with patch("lib.vibe.trackers.linear.logger") as mock_logger:
                    label_ids = tracker._get_or_create_label_ids("team_abc", ["Bug", "FailLabel"])

        assert label_ids == ["label-1"]
        # Should have warned about the failed creation and the count mismatch
        assert mock_logger.warning.call_count >= 1

    def test_get_or_create_warns_on_api_error(self) -> None:
        """A warning is logged when the API call fails."""
        tracker = LinearTracker(api_key="test-fake-key")

        # Make _get_label_ids return empty (simulating cache miss + failure)
        with patch.object(tracker, "_get_label_ids", return_value=[]):
            with patch.object(
                tracker,
                "_execute_query",
                side_effect=requests.RequestException("API error"),
            ):
                with patch("lib.vibe.trackers.linear.logger") as mock_logger:
                    label_ids = tracker._get_or_create_label_ids("team_abc", ["Bug"])

        assert label_ids == []
        mock_logger.warning.assert_called_once_with("Failed to resolve labels due to API error")


class TestLinearTrackerListLabels:
    """Tests for list_labels method."""

    def test_list_labels_success(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key", team_id="team_abc")
        mock_labels = [
            {"id": "label-1", "name": "Bug", "color": "#ff0000"},
            {"id": "label-2", "name": "Feature", "color": "#00ff00"},
        ]
        mock_response = {"data": {"issueLabels": {"nodes": mock_labels}}}

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            labels = tracker.list_labels()

        assert len(labels) == 2
        assert labels[0] == {"id": "label-1", "name": "Bug", "color": "#ff0000"}
        assert labels[1] == {"id": "label-2", "name": "Feature", "color": "#00ff00"}

    def test_list_labels_no_team(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_response = {"data": {"issueLabels": {"nodes": []}}}

        with patch.object(tracker, "_execute_query", return_value=mock_response) as mock_query:
            tracker.list_labels()

        # Should pass None for variables when no team_id
        call_args = mock_query.call_args
        assert call_args[0][1] is None

    def test_list_labels_exception(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")

        with patch.object(
            tracker, "_execute_query", side_effect=requests.RequestException("API error")
        ):
            labels = tracker.list_labels()

        assert labels == []


class TestLinearTrackerGetWorkflowStateId:
    """Tests for _get_workflow_state_id method."""

    def test_get_workflow_state_id_success(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_states = [
            {"id": "state-1", "name": "Backlog"},
            {"id": "state-2", "name": "Todo"},
            {"id": "state-3", "name": "In Progress"},
            {"id": "state-4", "name": "Done"},
        ]
        mock_response = {"data": {"team": {"states": {"nodes": mock_states}}}}

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            state_id = tracker._get_workflow_state_id("team_abc", "Done")

        assert state_id == "state-4"

    def test_get_workflow_state_id_case_insensitive(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")

        # Clear cache to avoid stale data from prior tests
        from lib.vibe.utils.cache import get_cache

        get_cache().invalidate("linear_states_team_abc")

        mock_states = [{"id": "state-1", "name": "In Progress"}]
        mock_response = {"data": {"team": {"states": {"nodes": mock_states}}}}

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            state_id = tracker._get_workflow_state_id("team_abc", "in progress")

        assert state_id == "state-1"

    def test_get_workflow_state_id_not_found(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")
        mock_states = [{"id": "state-1", "name": "Todo"}]
        mock_response = {"data": {"team": {"states": {"nodes": mock_states}}}}

        with patch.object(tracker, "_execute_query", return_value=mock_response):
            state_id = tracker._get_workflow_state_id("team_abc", "NonexistentState")

        assert state_id is None

    def test_get_workflow_state_id_exception(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key")

        # Clear cache to avoid stale data from prior tests
        from lib.vibe.utils.cache import get_cache

        get_cache().invalidate("linear_states_team_abc")

        with patch.object(
            tracker, "_execute_query", side_effect=requests.RequestException("API error")
        ):
            state_id = tracker._get_workflow_state_id("team_abc", "Done")

        assert state_id is None


class TestLinearTrackerParseIssue:
    """Tests for _parse_issue method."""

    def test_parse_issue_complete(self) -> None:
        tracker = LinearTracker()
        issue = {
            "id": "uuid-123",
            "identifier": "TEST-1",
            "title": "Test Issue",
            "description": "Test description",
            "state": {"name": "In Progress"},
            "labels": {"nodes": [{"name": "Bug"}, {"name": "High Risk"}]},
            "url": "https://linear.app/test/issue/TEST-1",
        }

        ticket = tracker._parse_issue(issue)

        assert ticket.id == "TEST-1"
        assert ticket.title == "Test Issue"
        assert ticket.description == "Test description"
        assert ticket.status == "In Progress"
        assert ticket.labels == ["Bug", "High Risk"]
        assert ticket.url == "https://linear.app/test/issue/TEST-1"
        assert ticket.raw == issue

    def test_parse_issue_missing_identifier_uses_id(self) -> None:
        tracker = LinearTracker()
        issue = {
            "id": "uuid-456",
            "title": "Issue without identifier",
            "description": "",
            "state": {"name": "Todo"},
            "labels": {"nodes": []},
            "url": "",
        }

        ticket = tracker._parse_issue(issue)

        assert ticket.id == "uuid-456"

    def test_parse_issue_no_state(self) -> None:
        tracker = LinearTracker()
        issue = {
            "id": "uuid-789",
            "identifier": "TEST-2",
            "title": "Issue",
            "description": "",
            "state": None,
            "labels": {"nodes": []},
            "url": "",
        }

        ticket = tracker._parse_issue(issue)

        assert ticket.status == ""

    def test_parse_issue_empty_labels(self) -> None:
        tracker = LinearTracker()
        issue = {
            "id": "uuid-abc",
            "identifier": "TEST-3",
            "title": "Issue",
            "description": "",
            "state": {"name": "Todo"},
            "labels": {"nodes": []},
            "url": "",
        }

        ticket = tracker._parse_issue(issue)

        assert ticket.labels == []

    def test_parse_issue_missing_labels_key(self) -> None:
        tracker = LinearTracker()
        issue = {
            "id": "uuid-def",
            "identifier": "TEST-4",
            "title": "Issue",
            "description": "",
            "state": {"name": "Todo"},
            "url": "",
        }

        ticket = tracker._parse_issue(issue)

        assert ticket.labels == []


class TestLinearTrackerSetParent:
    """Tests for set_parent method."""

    def test_set_parent_success(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key", team_id="team_abc")
        mock_child = {
            "id": "uuid-child",
            "identifier": "TEST-101",
            "title": "Child",
            "description": "",
            "state": {"name": "Todo"},
            "labels": {"nodes": []},
            "url": "https://linear.app/test/issue/TEST-101",
        }
        mock_parent = {
            "id": "uuid-parent",
            "identifier": "TEST-100",
            "title": "Parent",
            "description": "",
            "state": {"name": "Todo"},
            "labels": {"nodes": []},
            "url": "https://linear.app/test/issue/TEST-100",
        }
        mock_update_response = {"data": {"issueUpdate": {"success": True}}}

        call_count = {"n": 0}

        def mock_execute(query, variables=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # get_ticket for child
                return {"data": {"issue": mock_child}}
            elif call_count["n"] == 2:
                # get_ticket for parent
                return {"data": {"issue": mock_parent}}
            else:
                # issueUpdate
                return mock_update_response

        with patch.object(tracker, "_execute_query", side_effect=mock_execute):
            tracker.set_parent("TEST-101", "TEST-100")
        # Should complete without error

    def test_set_parent_child_not_found(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key", team_id="team_abc")

        with patch.object(tracker, "_execute_query", return_value={"data": {"issue": None}}):
            with pytest.raises(RuntimeError, match="Ticket not found: TEST-999"):
                tracker.set_parent("TEST-999", "TEST-100")

    def test_set_parent_parent_not_found(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key", team_id="team_abc")
        mock_child = {
            "id": "uuid-child",
            "identifier": "TEST-101",
            "title": "Child",
            "description": "",
            "state": {"name": "Todo"},
            "labels": {"nodes": []},
            "url": "",
        }

        call_count = {"n": 0}

        def mock_execute(query, variables=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {"data": {"issue": mock_child}}
            else:
                return {"data": {"issue": None}}

        with patch.object(tracker, "_execute_query", side_effect=mock_execute):
            with pytest.raises(RuntimeError, match="Parent ticket not found: TEST-999"):
                tracker.set_parent("TEST-101", "TEST-999")


class TestLinearTrackerAddRelation:
    """Tests for add_relation method."""

    def test_add_relation_delegates_to_create_relation(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key", team_id="team_abc")

        with patch.object(tracker, "create_relation") as mock_create_relation:
            tracker.add_relation("TEST-1", "TEST-2", "related")

        mock_create_relation.assert_called_once_with("TEST-1", "TEST-2", "related")

    def test_add_relation_blocks(self) -> None:
        tracker = LinearTracker(api_key="test-fake-key", team_id="team_abc")

        with patch.object(tracker, "create_relation") as mock_create_relation:
            tracker.add_relation("TEST-1", "TEST-2", "blocks")

        mock_create_relation.assert_called_once_with("TEST-1", "TEST-2", "blocks")
