"""SessionBridge: engine events (any thread) -> coalesced Qt signals on the GUI thread.

`session.subscribe(bridge.on_event)` once. `on_event` and `post` may be called from any
thread: they append to one locked FIFO (`eventqueue.EventQueue`) and, if no drain is
scheduled, emit the private `_wake` signal, connected with a queued connection to `_drain`
on the bridge's (GUI) thread. `_drain` coalesces (`eventqueue.coalesce`) and emits the typed
signals below; posted calls run in queue order between them, so a request done callback
comes after the `MATERIALIZED` event of the same computation.

Signals carry tuples of node ids. Ids in `nodes_removed` may be unknown to a view (a node
added and removed within one drain): ignore those.
"""

import logging
from typing import TYPE_CHECKING, Any

from prettyqt.qt import QtCore

from datacook.app.eventqueue import EventQueue, Posted, coalesce


if TYPE_CHECKING:
    from collections.abc import Callable

    from datacook.app.protocols import SessionLike
    from datacook.engine import Event


logger = logging.getLogger(__name__)

_MEMORY_KINDS = {"added", "removed", "invalidated", "materialized", "evicted", "reset"}


class SessionBridge(QtCore.QObject):
    nodes_added = QtCore.Signal(tuple)
    nodes_removed = QtCore.Signal(tuple)
    """The removed nodes incl. descendants."""
    nodes_changed = QtCore.Signal(tuple)
    """Params / name / comment changed."""
    nodes_moved = QtCore.Signal(tuple)
    """Nodes got new parents (a middle step was deleted / restored); INVALIDATED follows."""
    nodes_invalidated = QtCore.Signal(tuple)
    """Cached results outdated (edited node + descendants); a new generation each."""
    nodes_materialized = QtCore.Signal(tuple)
    nodes_evicted = QtCore.Signal(tuple)
    node_error = QtCore.Signal(str, object)
    """(failing node id, exception)."""
    memory_changed = QtCore.Signal()
    """Once per drain after anything that changes `session.memory()`."""
    structure_reset = QtCore.Signal()
    """Too many events at once (project load): rebuild views from the session."""
    drained = QtCore.Signal()
    """After each drain (tests, coarse refreshes)."""

    _wake = QtCore.Signal()

    def __init__(self, session: SessionLike, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self.session = session
        self._queue = EventQueue()
        self._wake.connect(self._drain, QtCore.Qt.ConnectionType.QueuedConnection)
        self._signals: dict[str, Any] = {
            "added": self.nodes_added,
            "removed": self.nodes_removed,
            "changed": self.nodes_changed,
            "moved": self.nodes_moved,
            "invalidated": self.nodes_invalidated,
            "materialized": self.nodes_materialized,
            "evicted": self.nodes_evicted,
        }
        self._unsubscribe: Callable[[], None] | None = session.subscribe(self.on_event)

    # --- any thread --------------------------------------------------------------------
    def on_event(self, event: Event) -> None:
        """Engine callback (any thread)."""
        if self._queue.put(event):
            self._wake.emit()

    def post(self, fn: Callable[..., Any], *args: Any) -> None:
        """Run `fn(*args)` on the GUI thread, after everything queued before (any thread)."""
        if self._queue.put(Posted(fn, args)):
            self._wake.emit()

    # --- GUI thread --------------------------------------------------------------------
    def flush(self) -> None:
        """Drain now (GUI thread; tests and shutdown)."""
        self._drain()

    def pending(self) -> int:
        return len(self._queue)

    def close(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    def _drain(self) -> None:
        items = self._queue.take()
        if not items:
            return
        memory = False
        for batch in coalesce(items, self.session):
            if batch.kind == "call":
                assert batch.call is not None
                try:
                    batch.call.fn(*batch.call.args)
                except Exception:
                    logger.exception("posted call failed: %s", batch.call.fn)
                continue
            memory = memory or batch.kind in _MEMORY_KINDS
            if batch.kind == "reset":
                self.structure_reset.emit()
            elif batch.kind == "error":
                self.node_error.emit(batch.node_ids[0], batch.error)
            else:
                self._signals[batch.kind].emit(batch.node_ids)
        if memory:
            self.memory_changed.emit()
        self.drained.emit()
