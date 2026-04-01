"""Abstract base class for ticket trackers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Project:
    """Represents a project from a tracker."""

    id: str
    name: str
    description: str
    state: str  # e.g., "planned", "started", "completed", "canceled"
    url: str
    raw: dict[str, Any]


@dataclass
class Ticket:
    """Represents a ticket from any tracker."""

    id: str
    title: str
    description: str
    status: str
    labels: list[str]
    url: str
    raw: dict[str, Any]
    # Extended fields (optional, may be None for backwards compatibility)
    priority: int | None = None  # 0=none, 1=urgent, 2=high, 3=medium, 4=low
    assignee: str | None = None  # Assignee name
    project: str | None = None  # Project name
    project_id: str | None = None  # Project ID
    project_state: str | None = None  # Project state (planned, started, completed, canceled)
    parent_id: str | None = None  # Parent ticket identifier
    parent_title: str | None = None  # Parent ticket title
    children: list["Ticket"] = field(default_factory=list)  # Sub-tasks
    blocks: list[str] = field(default_factory=list)  # Ticket IDs this blocks
    blocked_by: list[str] = field(default_factory=list)  # Ticket IDs blocking this
    comments: list[dict] = field(default_factory=list)  # Loaded on demand


class TrackerBase(ABC):
    """Abstract base class for ticket tracker integrations."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the tracker name."""
        pass

    @abstractmethod
    def authenticate(self, **kwargs: Any) -> bool:
        """Authenticate with the tracker API."""
        pass

    @abstractmethod
    def get_ticket(self, ticket_id: str) -> Ticket | None:
        """Fetch a single ticket by ID."""
        pass

    @abstractmethod
    def list_tickets(
        self,
        status: str | None = None,
        labels: list[str] | None = None,
        limit: int = 50,
    ) -> list[Ticket]:
        """List tickets with optional filters."""
        pass

    @abstractmethod
    def create_ticket(
        self,
        title: str,
        description: str,
        labels: list[str] | None = None,
    ) -> Ticket:
        """Create a new ticket."""
        pass

    @abstractmethod
    def update_ticket(
        self,
        ticket_id: str,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        labels: list[str] | None = None,
    ) -> Ticket:
        """Update an existing ticket."""
        pass

    @staticmethod
    def _normalize_labels(label_names: list[str]) -> list[str]:
        """Split comma-separated label strings into individual labels.

        Handles the case where callers pass ["Bug,Frontend,Low Risk"] as a
        single string instead of separate strings.
        """
        normalized: list[str] = []
        for name in label_names:
            parts = [part.strip() for part in name.split(",")]
            normalized.extend(part for part in parts if part)
        return normalized

    def comment_ticket(self, ticket_id: str, body: str) -> None:
        """Add a comment to a ticket. Override in trackers that support comments."""
        raise NotImplementedError(f"Commenting is not supported by the {self.name} tracker.")

    def set_parent(self, ticket_id: str, parent_id: str) -> None:
        """Set a parent relationship (make ticket_id a sub-task of parent_id).

        Override in trackers that support hierarchical relationships.
        """
        raise NotImplementedError(
            f"Parent relationships are not supported by the {self.name} tracker."
        )

    def get_comments(self, ticket_id: str, limit: int = 20) -> list[dict]:
        """Fetch comments for a ticket.

        Returns list of dicts with keys: author, date, body, is_bot.
        Override in trackers that support comment retrieval.
        """
        raise NotImplementedError(f"Comment retrieval is not supported by the {self.name} tracker.")

    def add_relation(self, ticket_id: str, related_id: str, relation_type: str = "related") -> None:
        """Create a non-hierarchical relationship between two tickets.

        Args:
            ticket_id: First ticket identifier
            related_id: Second ticket identifier
            relation_type: Type of relation (e.g. "related", "blocks")

        Override in trackers that support issue relations.
        """
        raise NotImplementedError(f"Issue relations are not supported by the {self.name} tracker.")

    @abstractmethod
    def validate_config(self) -> tuple[bool, list[str]]:
        """Validate tracker configuration. Returns (is_valid, list of issues)."""
        pass
