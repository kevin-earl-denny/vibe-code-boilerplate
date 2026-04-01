"""Linear.app ticket tracker integration."""

import copy
import logging
import os
from typing import Any

import requests

from lib.vibe.trackers.base import Project, Ticket, TrackerBase
from lib.vibe.utils.cache import get_cache
from lib.vibe.utils.retry import with_retry

logger = logging.getLogger(__name__)

LINEAR_API_URL = "https://api.linear.app/graphql"

# Priority mapping: Linear uses integers, we expose friendly names
PRIORITY_MAP = {
    "none": 0,
    "urgent": 1,
    "high": 2,
    "medium": 3,
    "low": 4,
}
PRIORITY_NAMES = {v: k for k, v in PRIORITY_MAP.items()}


class LinearTracker(TrackerBase):
    """Linear.app integration."""

    def __init__(self, api_key: str | None = None, team_id: str | None = None):
        self._api_key = api_key or os.environ.get("LINEAR_API_KEY")
        self._team_id = team_id
        self._headers: dict[str, str] = {}
        if self._api_key:
            self._headers = {
                "Authorization": self._api_key,
                "Content-Type": "application/json",
            }

    @property
    def name(self) -> str:
        return "linear"

    def authenticate(self, **kwargs: Any) -> bool:
        """Authenticate with Linear API."""
        api_key = kwargs.get("api_key") or self._api_key
        if not api_key:
            return False

        self._api_key = api_key
        self._headers = {
            "Authorization": api_key,
            "Content-Type": "application/json",
        }

        # Test authentication
        query = """
        query {
            viewer {
                id
                name
            }
        }
        """
        try:
            response = self._execute_query(query)
            return "viewer" in response.get("data", {})
        except (requests.RequestException, RuntimeError):
            return False

    @with_retry()
    def _execute_query(self, query: str, variables: dict | None = None) -> dict[str, Any]:
        """Execute a GraphQL query against Linear API."""
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        response = requests.post(LINEAR_API_URL, headers=self._headers, json=payload, timeout=30)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        if "errors" in result:
            errors = result["errors"]
            msg = errors[0].get("message", "Unknown GraphQL error") if errors else "Unknown error"
            raise RuntimeError(f"Linear API error: {msg}")
        return result

    def get_ticket(self, ticket_id: str, include_children: bool = False) -> Ticket | None:
        """Fetch a single ticket by ID or identifier.

        Args:
            ticket_id: The ticket ID or identifier (e.g., "PROJ-123")
            include_children: If True, fetch sub-tasks (children)
        """
        # Build children fragment conditionally
        children_fragment = (
            """
                children {
                    nodes {
                        id
                        identifier
                        title
                        state { name }
                    }
                }
        """
            if include_children
            else ""
        )

        query = f"""
        query GetIssue($id: String!) {{
            issue(id: $id) {{
                id
                identifier
                title
                description
                state {{ id name }}
                team {{ id }}
                labels {{ nodes {{ id name }} }}
                url
                priority
                assignee {{ id name email }}
                project {{ id name state }}
                parent {{ id identifier title }}
                relations(first: 50) {{
                    nodes {{
                        id
                        type
                        relatedIssue {{
                            identifier
                            title
                            state {{ name }}
                        }}
                    }}
                }}
                {children_fragment}
            }}
        }}
        """
        try:
            result = self._execute_query(query, {"id": ticket_id})
            issue = result.get("data", {}).get("issue")
            if not issue:
                return None
            return self._parse_issue(issue, include_children=include_children)
        except (requests.RequestException, RuntimeError, KeyError):
            return None

    def list_tickets(
        self,
        status: str | None = None,
        labels: list[str] | None = None,
        limit: int = 50,
        project: str | None = None,
        parent: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
        unassigned: bool = False,
        view: str | None = None,
        unblocked: bool = False,
    ) -> list[Ticket]:
        """List tickets with optional filters, with automatic pagination.

        Args:
            status: Filter by status name (e.g., "In Progress", "Done")
            labels: Filter by label names
            limit: Maximum number of tickets to return
            project: Filter by project name
            parent: Filter by parent ticket identifier (shows sub-tasks)
            priority: Filter by priority ("urgent", "high", "medium", "low", "none")
            assignee: Filter by assignee name or "me" for current user
            unassigned: If True, show only unassigned tickets
            view: Name of a Linear custom view whose filters to apply
            unblocked: If True, exclude tickets that are blocked by other tickets
        """
        # Include inverseRelations when filtering for unblocked tickets
        relations_fragment = ""
        if unblocked:
            relations_fragment = "inverseRelations { nodes { type } }"

        query = f"""
        query ListIssues($first: Int!, $after: String, $filter: IssueFilter) {{
            issues(first: $first, after: $after, filter: $filter) {{
                nodes {{
                    id
                    identifier
                    title
                    description
                    state {{ name }}
                    labels {{ nodes {{ id name }} }}
                    url
                    priority
                    assignee {{ name }}
                    project {{ name state }}
                    parent {{ identifier }}
                    relations(first: 50) {{
                        nodes {{
                            id
                            type
                            relatedIssue {{
                                identifier
                                title
                                state {{ name }}
                            }}
                        }}
                    }}
                    {relations_fragment}
                }}
                pageInfo {{
                    hasNextPage
                    endCursor
                }}
            }}
        }}
        """

        # Start with view filter if provided
        filter_obj: dict[str, Any] = {}
        if view:
            filter_obj = self._get_view_filter(view)

        # Always scope to team
        if self._team_id:
            filter_obj["team"] = {"id": {"eq": self._team_id}}

        # Explicit CLI filters override/merge into view filter
        if status:
            filter_obj["state"] = {"name": {"eq": status}}
        if labels:
            filter_obj["labels"] = {"name": {"in": labels}}
        if project:
            project_id = self._get_project_id(project)
            if project_id:
                filter_obj["project"] = {"id": {"eq": project_id}}
        if parent:
            parent_ticket = self.get_ticket(parent)
            if parent_ticket:
                parent_uuid = parent_ticket.raw.get("id")
                if parent_uuid:
                    filter_obj["parent"] = {"id": {"eq": parent_uuid}}
        if priority:
            priority_int = PRIORITY_MAP.get(priority.lower())
            if priority_int is not None:
                filter_obj["priority"] = {"eq": priority_int}
        if unassigned:
            filter_obj["assignee"] = {"null": True}
        elif assignee:
            if assignee.lower() == "me":
                viewer_id = self._get_viewer_id()
                if viewer_id:
                    filter_obj["assignee"] = {"id": {"eq": viewer_id}}
            else:
                user_id = self._get_user_id_by_name(assignee)
                if user_id:
                    filter_obj["assignee"] = {"id": {"eq": user_id}}

        all_tickets: list[Ticket] = []
        cursor: str | None = None
        # Fetch extra when post-filtering to compensate for excluded tickets
        fetch_limit = limit * 3 if unblocked else limit
        page_size = min(fetch_limit, 50)

        try:
            while True:
                variables: dict[str, Any] = {"first": page_size}
                if cursor:
                    variables["after"] = cursor
                if filter_obj:
                    variables["filter"] = filter_obj

                result = self._execute_query(query, variables)
                data = result.get("data", {}).get("issues", {})
                issues = data.get("nodes", [])
                page_info = data.get("pageInfo", {})

                for issue in issues:
                    if unblocked and self._is_blocked(issue):
                        continue
                    all_tickets.append(self._parse_issue(issue))

                if len(all_tickets) >= limit:
                    return all_tickets[:limit]

                if not page_info.get("hasNextPage", False):
                    break

                cursor = page_info.get("endCursor")
                if not cursor:
                    break

            return all_tickets
        except (requests.RequestException, RuntimeError):
            return all_tickets  # Return what we have so far

    @staticmethod
    def _is_blocked(issue: dict) -> bool:
        """Check if an issue has incoming blocking relations."""
        inverse = issue.get("inverseRelations", {})
        for rel in inverse.get("nodes", []):
            if rel.get("type") == "blocks":
                return True
        return False

    def create_ticket(
        self,
        title: str,
        description: str,
        labels: list[str] | None = None,
        project: str | None = None,
        project_id: str | None = None,
        parent: str | None = None,
        parent_id: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
    ) -> Ticket:
        """Create a new ticket in Linear.

        Args:
            title: Ticket title
            description: Ticket description
            labels: List of label names to apply
            project: Project name to add ticket to
            project_id: Project UUID (alternative to name)
            parent: Parent ticket identifier (e.g., "PROJ-100") for sub-task
            parent_id: Parent ticket UUID (alternative to identifier)
            priority: Priority level ("urgent", "high", "medium", "low", "none")
            assignee: Assignee name or "me" for self-assignment
        """
        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    description
                    state { name }
                    labels { nodes { id name } }
                    url
                    priority
                    assignee { name }
                    project { id name state }
                    parent { identifier title }
                }
            }
        }
        """
        input_obj: dict[str, Any] = {
            "title": title,
            "description": description,
        }
        if self._team_id:
            input_obj["teamId"] = self._team_id
        if labels:
            label_ids = self._get_or_create_label_ids(self._team_id, labels)
            if label_ids:
                input_obj["labelIds"] = label_ids

        # Project support
        if project_id:
            input_obj["projectId"] = project_id
        elif project:
            resolved_project_id = self._get_project_id(project)
            if resolved_project_id:
                input_obj["projectId"] = resolved_project_id

        # Parent (sub-task) support
        if parent_id:
            input_obj["parentId"] = parent_id
        elif parent:
            parent_ticket = self.get_ticket(parent)
            if parent_ticket:
                parent_uuid = parent_ticket.raw.get("id")
                if parent_uuid:
                    input_obj["parentId"] = parent_uuid

        # Priority support
        if priority:
            priority_int = PRIORITY_MAP.get(priority.lower())
            if priority_int is not None:
                input_obj["priority"] = priority_int

        # Assignee support
        if assignee:
            if assignee.lower() == "me":
                viewer_id = self._get_viewer_id()
                if viewer_id:
                    input_obj["assigneeId"] = viewer_id
            else:
                user_id = self._get_user_id_by_name(assignee)
                if user_id:
                    input_obj["assigneeId"] = user_id

        result = self._execute_query(mutation, {"input": input_obj})
        issue = result.get("data", {}).get("issueCreate", {}).get("issue")
        if not issue:
            raise RuntimeError("Failed to create ticket")
        return self._parse_issue(issue)

    def update_ticket(
        self,
        ticket_id: str,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        labels: list[str] | None = None,
        project: str | None = None,
        project_id: str | None = None,
        remove_project: bool = False,
        parent: str | None = None,
        parent_id: str | None = None,
        remove_parent: bool = False,
        priority: str | None = None,
        assignee: str | None = None,
        unassign: bool = False,
    ) -> Ticket:
        """Update an existing ticket.

        Args:
            ticket_id: The ticket ID or identifier
            title: New title
            description: New description
            status: New status name
            labels: Labels to add (merged with existing labels)
            project: Project name to add ticket to
            project_id: Project UUID
            remove_project: If True, remove from current project
            parent: Parent ticket identifier for sub-task
            parent_id: Parent ticket UUID
            remove_parent: If True, remove parent (make standalone)
            priority: Priority level
            assignee: Assignee name or "me"
            unassign: If True, remove assignee
        """
        input_obj: dict[str, Any] = {}
        if title is not None:
            input_obj["title"] = title
        if description is not None:
            input_obj["description"] = description

        # Always resolve identifier to UUID – the issueUpdate mutation
        # requires the internal UUID, not the human-readable identifier
        # (e.g. "PROJ-123").  The issue() *query* accepts either form,
        # but mutations do not, so we must resolve up front.  This also
        # gives us team_id for status/label resolution.
        issue = self.get_ticket(ticket_id)
        if not issue:
            raise RuntimeError(f"Ticket not found: {ticket_id}")
        issue_uuid = issue.raw.get("id")
        if not issue_uuid:
            raise RuntimeError(f"Ticket {ticket_id} has no internal UUID; cannot update")

        if status:
            # Resolve status name to workflow state ID
            team_id = (issue.raw.get("team") or {}).get("id") or self._team_id
            if not team_id:
                raise RuntimeError("Cannot resolve status: issue has no team")
            state_id = self._get_workflow_state_id(team_id, status)
            if not state_id:
                raise RuntimeError(
                    f"No workflow state named '{status}' for this team. "
                    "Check state name in Linear (e.g. Done, Canceled, In Progress)."
                )
            input_obj["stateId"] = state_id

        if labels:
            team_id = (issue.raw.get("team") or {}).get("id") or self._team_id
            if team_id:
                new_label_ids = self._get_or_create_label_ids(team_id, labels)
                if new_label_ids:
                    # Merge with existing label IDs so --label is additive
                    existing_label_ids = [
                        node["id"]
                        for node in issue.raw.get("labels", {}).get("nodes", [])
                        if "id" in node
                    ]
                    merged = list(dict.fromkeys(existing_label_ids + new_label_ids))
                    input_obj["labelIds"] = merged

        # Project support
        if remove_project:
            input_obj["projectId"] = None
        elif project_id:
            input_obj["projectId"] = project_id
        elif project:
            resolved_project_id = self._get_project_id(project)
            if resolved_project_id:
                input_obj["projectId"] = resolved_project_id

        # Parent (sub-task) support
        if remove_parent:
            input_obj["parentId"] = None
        elif parent_id:
            input_obj["parentId"] = parent_id
        elif parent:
            parent_ticket = self.get_ticket(parent)
            if parent_ticket:
                parent_uuid = parent_ticket.raw.get("id")
                if parent_uuid:
                    input_obj["parentId"] = parent_uuid

        # Priority support
        if priority:
            priority_int = PRIORITY_MAP.get(priority.lower())
            if priority_int is not None:
                input_obj["priority"] = priority_int

        # Assignee support
        if unassign:
            input_obj["assigneeId"] = None
        elif assignee:
            if assignee.lower() == "me":
                viewer_id = self._get_viewer_id()
                if viewer_id:
                    input_obj["assigneeId"] = viewer_id
            else:
                user_id = self._get_user_id_by_name(assignee)
                if user_id:
                    input_obj["assigneeId"] = user_id

        mutation = """
        mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    description
                    state { name }
                    labels { nodes { id name } }
                    url
                    priority
                    assignee { name }
                    project { id name state }
                    parent { identifier title }
                }
            }
        }
        """
        result = self._execute_query(mutation, {"id": issue_uuid, "input": input_obj})
        issue = result.get("data", {}).get("issueUpdate", {}).get("issue")
        if not issue:
            raise RuntimeError("Failed to update ticket")
        return self._parse_issue(issue)

    def comment_ticket(self, ticket_id: str, body: str) -> None:
        """Add a comment to a Linear issue."""
        issue = self.get_ticket(ticket_id)
        if not issue:
            raise RuntimeError(f"Ticket not found: {ticket_id}")
        issue_uuid = issue.raw.get("id")
        if not issue_uuid:
            raise RuntimeError("Cannot comment: issue has no id")

        mutation = """
        mutation CreateComment($input: CommentCreateInput!) {
            commentCreate(input: $input) {
                success
                comment { id }
            }
        }
        """
        self._execute_query(
            mutation,
            {"input": {"issueId": issue_uuid, "body": body}},
        )

    def get_comments(self, ticket_id: str, limit: int = 20) -> list[dict]:
        """Fetch comments for a Linear issue.

        Returns list of dicts with keys: author, date, body, is_bot.
        """
        issue = self.get_ticket(ticket_id)
        if not issue:
            raise RuntimeError(f"Ticket not found: {ticket_id}")
        issue_uuid = issue.raw.get("id")
        if not issue_uuid:
            raise RuntimeError("Cannot fetch comments: issue has no id")

        query = """
        query GetComments($id: String!, $first: Int!) {
            issue(id: $id) {
                comments(first: $first) {
                    nodes {
                        body
                        createdAt
                        user { name }
                        botActor { name }
                    }
                }
            }
        }
        """
        result = self._execute_query(query, {"id": issue_uuid, "first": limit})
        nodes = result.get("data", {}).get("issue", {}).get("comments", {}).get("nodes", [])

        comments = []
        for node in nodes:
            is_bot = node.get("botActor") is not None
            if is_bot:
                author = f"Bot: {node['botActor'].get('name', 'Unknown')}"
            else:
                author = (node.get("user") or {}).get("name", "Unknown")
            comments.append(
                {
                    "author": author,
                    "date": node.get("createdAt", ""),
                    "body": node.get("body", ""),
                    "is_bot": is_bot,
                }
            )
        return comments

    def validate_config(self) -> tuple[bool, list[str]]:
        """Validate Linear configuration."""
        issues = []

        if not self._api_key:
            issues.append("LINEAR_API_KEY not set")

        if not self._team_id:
            issues.append("Linear team ID not configured")

        if self._api_key and not self.authenticate():
            issues.append("LINEAR_API_KEY is invalid or expired")

        return len(issues) == 0, issues

    def _get_label_ids(self, team_id: str | None, label_names: list[str]) -> list[str]:
        """Resolve label names to Linear label IDs for the team."""
        if not team_id or not label_names:
            return []
        label_names = self._normalize_labels(label_names)

        # Try cache first
        cache = get_cache()
        cache_key = f"linear_labels_{team_id}"
        cached_labels = cache.get(cache_key)

        if cached_labels is not None:
            name_to_id = {n["name"].lower(): n["id"] for n in cached_labels}
            return [name_to_id[n.lower()] for n in label_names if n.lower() in name_to_id]

        query = """
        query TeamLabels($teamId: String!) {
            team(id: $teamId) {
                labels(first: 250) { nodes { id name } }
            }
        }
        """
        try:
            result = self._execute_query(query, {"teamId": team_id})
            nodes = result.get("data", {}).get("team", {}).get("labels", {}).get("nodes", [])

            # Cache the raw label data
            cache.set(
                cache_key,
                [{"name": n.get("name", ""), "id": n["id"]} for n in nodes if n.get("id")],
            )

            name_to_id = {n.get("name", "").lower(): n["id"] for n in nodes if n.get("id")}
            return [name_to_id[n.lower()] for n in label_names if n.lower() in name_to_id]
        except (requests.RequestException, RuntimeError):
            return []

    def _get_or_create_label_ids(self, team_id: str | None, label_names: list[str]) -> list[str]:
        """Resolve label names to IDs, creating any that don't exist."""
        if not team_id or not label_names:
            return []
        label_names = self._normalize_labels(label_names)
        # First try to resolve all labels (uses cache internally)
        existing_ids = self._get_label_ids(team_id, label_names)
        if len(existing_ids) == len(label_names):
            return existing_ids

        # Some labels are missing — figure out which ones and create them.
        # Invalidate cache since we know it's stale (missing labels).
        cache = get_cache()
        cache_key = f"linear_labels_{team_id}"
        cache.invalidate(cache_key)

        query = """
        query TeamLabels($teamId: String!) {
            team(id: $teamId) {
                labels(first: 250) { nodes { id name } }
            }
        }
        """
        try:
            result = self._execute_query(query, {"teamId": team_id})
            nodes = result.get("data", {}).get("team", {}).get("labels", {}).get("nodes", [])
            name_to_id = {n.get("name", "").lower(): n["id"] for n in nodes if n.get("id")}

            label_ids = []
            created_any = False
            for name in label_names:
                if name.lower() in name_to_id:
                    label_ids.append(name_to_id[name.lower()])
                else:
                    new_id = self._create_label(team_id, name)
                    if new_id:
                        label_ids.append(new_id)
                        created_any = True
                    else:
                        logger.warning("Failed to create label '%s' for team %s", name, team_id)

            # Re-cache the updated label set if we created new labels
            if created_any:
                cache.invalidate(cache_key)

            if len(label_ids) < len(label_names):
                applied = len(label_ids)
                requested = len(label_names)
                logger.warning("Only %d of %d requested labels were applied", applied, requested)

            return label_ids
        except (requests.RequestException, RuntimeError):
            logger.warning("Failed to resolve labels due to API error")
            return existing_ids

    def _create_label(self, team_id: str, name: str) -> str | None:
        """Create a label in Linear and return its ID."""
        mutation = """
        mutation CreateLabel($input: IssueLabelCreateInput!) {
            issueLabelCreate(input: $input) {
                success
                issueLabel { id name }
            }
        }
        """
        try:
            result = self._execute_query(mutation, {"input": {"name": name, "teamId": team_id}})
            label = result.get("data", {}).get("issueLabelCreate", {}).get("issueLabel")
            return label.get("id") if label else None
        except (requests.RequestException, RuntimeError):
            return None

    def list_labels(self) -> list[dict[str, str]]:
        """List all labels with their IDs for the configured team."""
        query = """
        query ListLabels($teamId: String) {
            issueLabels(filter: { team: { id: { eq: $teamId } } }, first: 250) {
                nodes {
                    id
                    name
                    color
                }
            }
        }
        """
        variables = {}
        if self._team_id:
            variables["teamId"] = self._team_id

        try:
            result = self._execute_query(query, variables if variables else None)
            nodes = result.get("data", {}).get("issueLabels", {}).get("nodes", [])
            return [
                {
                    "id": node.get("id", ""),
                    "name": node.get("name", ""),
                    "color": node.get("color", ""),
                }
                for node in nodes
            ]
        except (requests.RequestException, RuntimeError):
            return []

    def _get_workflow_state_id(self, team_id: str, state_name: str) -> str | None:
        """Resolve workflow state name to state ID for a team."""
        cache = get_cache()
        cache_key = f"linear_states_{team_id}"
        cached_states = cache.get(cache_key)

        if cached_states is not None:
            for s in cached_states:
                if s.get("name", "").lower() == state_name.lower():
                    state_id: str | None = s.get("id")
                    return state_id
            return None

        query = """
        query WorkflowStates($teamId: String!) {
            team(id: $teamId) {
                states {
                    nodes {
                        id
                        name
                    }
                }
            }
        }
        """
        try:
            result = self._execute_query(query, {"teamId": team_id})
            nodes = result.get("data", {}).get("team", {}).get("states", {}).get("nodes", [])

            # Cache the states
            cache.set(
                cache_key,
                [{"id": n.get("id", ""), "name": n.get("name", "")} for n in nodes],
            )

            for node in nodes:
                if node.get("name", "").lower() == state_name.lower():
                    node_id: str | None = node.get("id")
                    return node_id
            return None
        except (requests.RequestException, RuntimeError):
            return None

    def create_relation(
        self,
        blocker_id: str,
        blocked_id: str,
        relation_type: str = "blocks",
    ) -> bool:
        """Create a blocking relationship between two issues.

        Args:
            blocker_id: The issue that blocks (prerequisite)
            blocked_id: The issue that is blocked (dependent)
            relation_type: Type of relation ("blocks" or "related")

        Returns:
            True if relation was created successfully
        """
        # First resolve identifiers to UUIDs if needed
        blocker = self.get_ticket(blocker_id)
        blocked = self.get_ticket(blocked_id)

        if not blocker:
            raise RuntimeError(f"Ticket not found: {blocker_id}")
        if not blocked:
            raise RuntimeError(f"Ticket not found: {blocked_id}")

        blocker_uuid = blocker.raw.get("id")
        blocked_uuid = blocked.raw.get("id")

        if not blocker_uuid or not blocked_uuid:
            raise RuntimeError("Cannot create relation: missing issue UUIDs")

        mutation = """
        mutation CreateIssueRelation($input: IssueRelationCreateInput!) {
            issueRelationCreate(input: $input) {
                success
                issueRelation {
                    id
                    type
                }
            }
        }
        """

        input_obj = {
            "issueId": blocker_uuid,
            "relatedIssueId": blocked_uuid,
            "type": relation_type,
        }

        try:
            result = self._execute_query(mutation, {"input": input_obj})
            success: bool = (
                result.get("data", {}).get("issueRelationCreate", {}).get("success", False)
            )
            return success
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to create relation: {e}") from e

    def set_parent(self, ticket_id: str, parent_id: str) -> None:
        """Set a parent relationship (make ticket_id a sub-task of parent_id).

        Uses the Linear issueUpdate mutation to set the parentId field.

        Args:
            ticket_id: The child ticket identifier (e.g. "PROJ-101")
            parent_id: The parent ticket identifier (e.g. "PROJ-100")
        """
        child = self.get_ticket(ticket_id)
        if not child:
            raise RuntimeError(f"Ticket not found: {ticket_id}")

        parent = self.get_ticket(parent_id)
        if not parent:
            raise RuntimeError(f"Parent ticket not found: {parent_id}")

        child_uuid = child.raw.get("id")
        parent_uuid = parent.raw.get("id")
        if not child_uuid or not parent_uuid:
            raise RuntimeError("Cannot set parent: missing issue UUIDs")

        mutation = """
        mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                success
            }
        }
        """
        try:
            result = self._execute_query(
                mutation,
                {"id": child_uuid, "input": {"parentId": parent_uuid}},
            )
            success = result.get("data", {}).get("issueUpdate", {}).get("success", False)
            if not success:
                raise RuntimeError(f"Failed to set parent for {ticket_id}")
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to set parent: {e}") from e

    def add_relation(self, ticket_id: str, related_id: str, relation_type: str = "related") -> None:
        """Create a non-hierarchical relationship between two Linear issues.

        Delegates to create_relation with the appropriate relation_type.

        Args:
            ticket_id: First ticket identifier
            related_id: Second ticket identifier
            relation_type: Type of relation ("related" or "blocks")
        """
        self.create_relation(ticket_id, related_id, relation_type)

    def _parse_issue(self, issue: dict, include_children: bool = False) -> Ticket:
        """Parse a Linear issue into a Ticket."""
        state = issue.get("state") or {}
        assignee = issue.get("assignee") or {}
        project = issue.get("project") or {}
        parent = issue.get("parent") or {}

        # Parse children if present
        children: list[Ticket] = []
        if include_children and "children" in issue:
            children_nodes = issue.get("children", {}).get("nodes", [])
            children = [self._parse_issue(child) for child in children_nodes]

        # Parse blocking relationships from relations
        blocks: list[str] = []
        blocked_by: list[str] = []
        relations_nodes = issue.get("relations", {}).get("nodes", [])
        for rel in relations_nodes:
            rel_type = rel.get("type", "")
            related = rel.get("relatedIssue") or {}
            identifier = related.get("identifier", "")
            if not identifier:
                continue
            if rel_type == "blocks":
                blocks.append(identifier)
            elif rel_type == "blocked_by":
                blocked_by.append(identifier)

        return Ticket(
            id=issue.get("identifier", issue.get("id", "")),
            title=issue.get("title", ""),
            description=issue.get("description", ""),
            status=state.get("name", ""),
            labels=[label["name"] for label in issue.get("labels", {}).get("nodes", [])],
            url=issue.get("url", ""),
            raw=issue,
            priority=issue.get("priority"),
            assignee=assignee.get("name"),
            project=project.get("name"),
            project_id=project.get("id"),
            project_state=project.get("state"),
            parent_id=parent.get("identifier"),
            parent_title=parent.get("title"),
            children=children,
            blocks=blocks,
            blocked_by=blocked_by,
        )

    # -------------------------------------------------------------------------
    # Custom Views
    # -------------------------------------------------------------------------

    def list_views(self) -> list[dict[str, Any]]:
        """Fetch all custom views from Linear.

        Returns a list of dicts with keys: name, id, filterData, owner.
        Results are cached for 30 minutes.
        """
        cache = get_cache()
        cache_key = "linear_custom_views"
        cached = cache.get(cache_key)
        if cached is not None:
            result_views: list[dict[str, Any]] = cached
            return result_views

        query = """
        query ListCustomViews {
            customViews {
                nodes {
                    id
                    name
                    filterData
                    owner { name }
                }
            }
        }
        """
        try:
            result = self._execute_query(query)
            nodes = result.get("data", {}).get("customViews", {}).get("nodes", [])
            views = [
                {
                    "id": v.get("id", ""),
                    "name": v.get("name", ""),
                    "filterData": v.get("filterData", {}),
                    "owner": (v.get("owner") or {}).get("name", ""),
                }
                for v in nodes
            ]
            cache.set(cache_key, views, ttl=1800)
            return views
        except (requests.RequestException, RuntimeError) as e:
            raise RuntimeError(f"Failed to fetch custom views: {e}") from e

    def _get_view_filter(self, view_name: str) -> dict[str, Any]:
        """Get the filterData for a named custom view.

        Raises RuntimeError if the view is not found or is ambiguous.
        """
        views = self.list_views()
        name_lower = view_name.lower()
        matches = [v for v in views if v["name"].lower() == name_lower]

        if not matches:
            available = ", ".join(sorted(v["name"] for v in views)) or "(none)"
            raise RuntimeError(f"Custom view '{view_name}' not found. Available views: {available}")

        if len(matches) > 1:
            owners = ", ".join(f"'{m['name']}' (owner: {m['owner']})" for m in matches)
            raise RuntimeError(
                f"Multiple views match '{view_name}': {owners}. Use the exact name to disambiguate."
            )

        filter_data: dict[str, Any] = matches[0].get("filterData", {})
        return copy.deepcopy(filter_data)

    # -------------------------------------------------------------------------
    # Project Management
    # -------------------------------------------------------------------------

    def list_projects(
        self,
        state: str | None = None,
        limit: int = 50,
    ) -> list[Project]:
        """List projects accessible to the team.

        Args:
            state: Filter by project state ("planned", "started", "completed", "canceled")
            limit: Maximum number of projects to return
        """
        query = """
        query ListProjects($first: Int!, $filter: ProjectFilter) {
            projects(first: $first, filter: $filter) {
                nodes {
                    id
                    name
                    description
                    state
                    url
                    startDate
                    targetDate
                }
            }
        }
        """
        filter_obj: dict[str, Any] = {}
        if self._team_id:
            filter_obj["accessibleTeams"] = {"id": {"eq": self._team_id}}
        if state:
            filter_obj["state"] = {"eq": state}

        variables: dict[str, Any] = {"first": limit}
        if filter_obj:
            variables["filter"] = filter_obj

        try:
            result = self._execute_query(query, variables)
            nodes = result.get("data", {}).get("projects", {}).get("nodes", [])
            return [self._parse_project(p) for p in nodes]
        except (requests.RequestException, RuntimeError):
            return []

    def get_project(self, project_id: str) -> Project | None:
        """Get a project by ID or name.

        Args:
            project_id: Project UUID or name
        """
        # Try by ID first
        query = """
        query GetProject($id: String!) {
            project(id: $id) {
                id
                name
                description
                state
                url
                startDate
                targetDate
            }
        }
        """
        try:
            result = self._execute_query(query, {"id": project_id})
            project = result.get("data", {}).get("project")
            if project:
                return self._parse_project(project)
        except (requests.RequestException, RuntimeError):
            pass

        # Try by name
        projects = self.list_projects()
        for p in projects:
            if p.name.lower() == project_id.lower():
                return p
        return None

    def create_project(
        self,
        name: str,
        description: str = "",
        state: str = "planned",
    ) -> Project:
        """Create a new project.

        Args:
            name: Project name
            description: Project description
            state: Initial state ("planned", "started", "completed", "canceled")
        """
        mutation = """
        mutation CreateProject($input: ProjectCreateInput!) {
            projectCreate(input: $input) {
                success
                project {
                    id
                    name
                    description
                    state
                    url
                }
            }
        }
        """
        input_obj: dict[str, Any] = {
            "name": name,
            "description": description,
            "state": state,
        }
        if self._team_id:
            input_obj["teamIds"] = [self._team_id]

        result = self._execute_query(mutation, {"input": input_obj})
        project = result.get("data", {}).get("projectCreate", {}).get("project")
        if not project:
            raise RuntimeError("Failed to create project")
        return self._parse_project(project)

    def _parse_project(self, project: dict) -> Project:
        """Parse a Linear project into a Project."""
        return Project(
            id=project.get("id", ""),
            name=project.get("name", ""),
            description=project.get("description", ""),
            state=project.get("state", ""),
            url=project.get("url", ""),
            raw=project,
        )

    def _get_project_id(self, project_name: str) -> str | None:
        """Resolve project name to ID."""
        projects = self.list_projects()
        for p in projects:
            if p.name.lower() == project_name.lower():
                return p.id
        return None

    # -------------------------------------------------------------------------
    # User Management (for assignee support)
    # -------------------------------------------------------------------------

    def _get_viewer_id(self) -> str | None:
        """Get the current authenticated user's ID."""
        cache = get_cache()
        cache_key = "linear_viewer"
        cached_viewer = cache.get(cache_key)

        if cached_viewer is not None:
            result_viewer: str = cached_viewer
            return result_viewer

        query = """
        query {
            viewer {
                id
            }
        }
        """
        try:
            result = self._execute_query(query)
            viewer_id: str | None = result.get("data", {}).get("viewer", {}).get("id")
            if viewer_id:
                cache.set(cache_key, viewer_id, ttl=1800)  # 30 min TTL
            return viewer_id
        except (requests.RequestException, RuntimeError):
            return None

    def _get_user_id_by_name(self, name: str) -> str | None:
        """Find a user ID by name or email."""
        query = """
        query {
            users {
                nodes {
                    id
                    name
                    email
                    displayName
                }
            }
        }
        """
        try:
            result = self._execute_query(query)
            users = result.get("data", {}).get("users", {}).get("nodes", [])
            name_lower = name.lower()
            for user in users:
                if (
                    user.get("name", "").lower() == name_lower
                    or user.get("email", "").lower() == name_lower
                    or user.get("displayName", "").lower() == name_lower
                ):
                    user_id: str | None = user.get("id")
                    return user_id
            return None
        except (requests.RequestException, RuntimeError):
            return None

    def list_users(self) -> list[dict[str, str]]:
        """List all users in the organization."""
        cache = get_cache()
        cache_key = "linear_users"
        cached_users = cache.get(cache_key)

        if cached_users is not None:
            users_result: list[dict[str, str]] = cached_users
            return users_result

        query = """
        query {
            users {
                nodes {
                    id
                    name
                    email
                    displayName
                    active
                }
            }
        }
        """
        try:
            result = self._execute_query(query)
            users = result.get("data", {}).get("users", {}).get("nodes", [])
            user_list = [
                {
                    "id": u.get("id", ""),
                    "name": u.get("name", ""),
                    "email": u.get("email", ""),
                    "display_name": u.get("displayName", ""),
                    "active": u.get("active", True),
                }
                for u in users
            ]
            cache.set(cache_key, user_list, ttl=1800)  # 30 min TTL
            return user_list
        except (requests.RequestException, RuntimeError):
            return []
