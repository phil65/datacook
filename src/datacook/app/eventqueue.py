"""Thread-safe event queue and coalescing for `SessionBridge` (Qt-free).

Engine events (any thread) and posted calls (`Posted`, e.g. request done callbacks from a
worker) go into one FIFO. The GUI thread takes everything queued so far and turns it into
`Batch`es: runs of events of the same kind are merged, events for nodes that no longer exist
or whose generation is outdated are dropped, and posted calls stay where they were queued,
so a done callback always comes after the `MATERIALIZED` event of the same computation.
"""

import collections
from dataclasses import dataclass
import threading
from typing import TYPE_CHECKING, Any, Literal

from datacook.engine import Event, EventKind


if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from datacook.app.protocols import SessionLike


RESET_THRESHOLD = 200
"""More engine events than this in one drain (e.g. a project load) -> one `reset` batch."""


@dataclass(frozen=True, slots=True)
class Posted:
    """A call to run on the GUI thread, in queue order."""

    fn: Callable[..., Any]
    args: tuple[Any, ...] = ()


type BatchKind = Literal[
    "added",
    "removed",
    "changed",
    "moved",
    "invalidated",
    "materialized",
    "evicted",
    "error",
    "reset",
    "call",
]


@dataclass(frozen=True, slots=True)
class Batch:
    """One coalesced signal: `kind` + node ids (+ error / posted call)."""

    kind: BatchKind
    node_ids: tuple[str, ...] = ()
    error: BaseException | None = None
    call: Posted | None = None


class EventQueue:
    """A deque guarded by an explicit lock (no reliance on deque atomicity / the GIL)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: collections.deque[Event | Posted] = collections.deque()
        self._scheduled = False

    def put(self, item: Event | Posted) -> bool:
        """Append; True if the consumer must be woken (no drain is scheduled yet)."""
        with self._lock:
            self._items.append(item)
            if self._scheduled:
                return False
            self._scheduled = True
            return True

    def take(self) -> list[Event | Posted]:
        """Everything queued so far; the next `put` schedules a new drain."""
        with self._lock:
            items = list(self._items)
            self._items.clear()
            self._scheduled = False
            return items

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


_KINDS: dict[EventKind, BatchKind] = {
    EventKind.ADDED: "added",
    EventKind.REMOVED: "removed",
    EventKind.CHANGED: "changed",
    EventKind.MOVED: "moved",
    EventKind.INVALIDATED: "invalidated",
    EventKind.MATERIALIZED: "materialized",
    EventKind.EVICTED: "evicted",
    EventKind.ERROR: "error",
}


def coalesce(items: Sequence[Event | Posted], session: SessionLike) -> list[Batch]:
    """Turn queued items into batches (see module docstring). GUI thread."""
    n_events = sum(1 for i in items if isinstance(i, Event))
    if n_events > RESET_THRESHOLD:
        # one reset instead of many small updates; errors and posted calls still go out
        out = [Batch("reset")]
        for item in items:
            if isinstance(item, Posted):
                out.append(Batch("call", call=item))
            elif item.kind == EventKind.ERROR and _current(item, session):
                out.append(Batch("error", item.node_ids, item.error))
        return out
    out = []
    for item in items:
        if isinstance(item, Posted):
            out.append(Batch("call", call=item))
            continue
        kind = _KINDS[item.kind]
        ids = _alive_ids(item, session)
        if not ids:
            continue
        if kind == "error":
            out.append(Batch("error", ids, item.error))
        elif out and out[-1].kind == kind:
            merged = tuple(dict.fromkeys((*out[-1].node_ids, *ids)))
            out[-1] = Batch(kind, merged)
        else:
            out.append(Batch(kind, ids))
    return out


def _alive_ids(event: Event, session: SessionLike) -> tuple[str, ...]:
    match event.kind:
        case EventKind.REMOVED | EventKind.EVICTED:
            # removed nodes are gone by definition; eviction is about the cache only
            return event.node_ids
        case EventKind.MATERIALIZED | EventKind.ERROR:
            return event.node_ids if _current(event, session) else ()
        case _:
            gens = session.generations(event.node_ids)
            return tuple(n for n in event.node_ids if n in gens)


def _current(event: Event, session: SessionLike) -> bool:
    """The event's node still exists and has the event's generation."""
    gens = session.generations(event.node_ids[:1])
    return gens.get(event.node_id) == event.generation
