"""Session events (plain callbacks, no Qt)."""

from dataclasses import dataclass
from enum import StrEnum


class EventKind(StrEnum):
    ADDED = "added"
    """A node was added (`node_ids` = the new node)."""
    REMOVED = "removed"
    """Nodes were removed (`node_ids` = the node and all its descendants)."""
    CHANGED = "changed"
    """A node's params / name / comment changed (`node_ids` = the node)."""
    MOVED = "moved"
    """Nodes got new parents (`node_ids` = the re-parented nodes); followed by INVALIDATED."""
    INVALIDATED = "invalidated"
    """Cached results are outdated (`node_ids` = the edited node + all descendants)."""
    MATERIALIZED = "materialized"
    """A node's frame was computed and cached for `generation`."""
    EVICTED = "evicted"
    """Frames were dropped from the cache (memory budget); summaries stay available."""
    ERROR = "error"
    """Computing a node failed (`error` holds the exception)."""


@dataclass(frozen=True, slots=True)
class Event:
    kind: EventKind
    node_ids: tuple[str, ...]
    generation: int | None = None
    error: BaseException | None = None

    @property
    def node_id(self) -> str:
        return self.node_ids[0]
