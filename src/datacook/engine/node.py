"""Tree nodes: immutable snapshots of (parents, op record, metadata)."""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING
import uuid


if TYPE_CHECKING:
    from datacook.engine.ops.base import OpRecord


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass(frozen=True, slots=True)
class Node:
    """One step of the tree. Never holds a frame: the `Session` computes and caches those.

    `generation` changes whenever the node's data changes (its params or an ancestor's
    params were edited); results computed for an older generation are stale. The session
    draws generations from one monotonic counter, so a value is never reused.
    Nodes are immutable: the session replaces them on edits, so a `Node` handed to
    another thread stays consistent.
    """

    id: str
    record: OpRecord
    parents: tuple[str, ...] = ()
    name: str | None = None
    comment: str | None = None
    generation: int = 0

    @property
    def op_id(self) -> str:
        return self.record.op_id

    def evolve(self, **changes: object) -> Node:
        return replace(self, **changes)
