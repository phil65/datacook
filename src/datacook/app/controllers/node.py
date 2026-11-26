"""NodeController: the "current" view slot, its pins and its computation (GUI thread only).

Select flow (design §3): `AppState.current = n` -> pins move to n + its parents at once ->
a cache hit is shown immediately; otherwise the slot goes to LOADING (last known shape from
`session.summary`) and after the selection debounce one request starts in the "current"
job slot (cancelling the previous one). Results for another node or an old generation are
dropped. Invalidation of the shown node drops its frame (STALE) and recomputes; an explicit
drop shows EVICTED (no automatic re-request, `recompute()` does it); a failed request shows
ERROR with the failing step (`slot.error_node`, may be an ancestor).
"""

from typing import TYPE_CHECKING

from prettyqt.qt import QtCore

from datacook.app.slots import SlotState, ViewSlot
from datacook.engine import Cancelled


if TYPE_CHECKING:
    from datacook.app.bridge import SessionBridge
    from datacook.app.jobs import JobRunner
    from datacook.app.pins import PinBook
    from datacook.app.protocols import RequestLike, SessionLike
    from datacook.app.state import AppState


SLOT = "current"


class NodeController(QtCore.QObject):
    def __init__(
        self,
        session: SessionLike,
        state: AppState,
        bridge: SessionBridge,
        jobs: JobRunner,
        pins: PinBook,
        parent: QtCore.QObject | None = None,
    ):
        super().__init__(parent)
        self.session = session
        self.state = state
        self.jobs = jobs
        self.pins = pins
        self.slot = ViewSlot(SLOT, parent=self)
        self._lineage: tuple[str, ...] = ()
        """Ancestors of the current node (parents first), for the fallback on removal."""
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._request_current)
        state.current_changed.connect(self._on_current_changed)
        bridge.nodes_removed.connect(self._on_removed)
        bridge.nodes_moved.connect(self._on_moved)
        bridge.nodes_invalidated.connect(self._on_invalidated)
        bridge.nodes_evicted.connect(self._on_evicted)
        bridge.nodes_materialized.connect(self._on_materialized)
        bridge.structure_reset.connect(self._on_reset)

    # --- public ------------------------------------------------------------------------
    def recompute(self) -> None:
        """Compute the current node now (overlay button "Recompute")."""
        nid = self.state.current
        if nid is None or nid not in self.session:
            return
        self._timer.stop()
        self.slot.set_loading(nid, self.session.summary(nid) or self.slot.summary)
        self._request_current()

    def held_ids(self) -> frozenset[str]:
        held = self.slot.held_id
        return frozenset() if held is None else frozenset({held})

    def close(self) -> None:
        self._timer.stop()
        self.jobs.cancel(SLOT)
        self.slot.clear()
        self.pins.release(SLOT)

    # --- flow --------------------------------------------------------------------------
    def _on_current_changed(self, _old: str | None, new: str | None) -> None:
        self._timer.stop()
        node = None if new is None else self.session.get(new)
        if node is None:
            self.jobs.cancel(SLOT)
            self.slot.clear()
            self.pins.release(SLOT)
            self._lineage = ()
            return
        # pins first (cheap): the node and its inputs stay in memory while shown
        self.pins.set(SLOT, (node.id, *node.parents))
        self._lineage = tuple(a.id for a in self.session.ancestors(node.id) if a.id != node.id)
        self._show_or_request(node.id, debounce=True)

    def _show_or_request(self, nid: str, *, debounce: bool, stale: bool = False) -> None:
        self.jobs.cancel(SLOT)
        if self._show_cached(nid):
            return
        if (error := self.session.error(nid)) is not None:
            # failed for this generation already: show it, "Recompute" retries
            self.slot.set_error(nid, error, self._failing_node(nid), self._generation(nid))
            return
        if stale:
            self.slot.set_stale()
        else:
            self.slot.set_loading(nid, self.session.summary(nid))
        delay = self.state.settings.selection_debounce_ms
        if debounce and delay > 0:
            self._timer.start(delay)
        else:
            self._request_current()

    def _show_cached(self, nid: str) -> bool:
        # the node is pinned, so a cache hit cannot be evicted before `materialize` reads it
        if not self.session.is_cached(nid):
            return False
        self.slot.show(
            nid, self.session.materialize(nid), self._generation(nid), self.session.summary(nid)
        )
        return True

    def _request_current(self) -> None:
        nid = self.state.current
        if nid is None or nid not in self.session:
            return
        self.jobs.request(SLOT, nid, self._on_done)

    def _on_done(self, req: RequestLike) -> None:
        nid = req.node_id
        if nid is None or nid != self.state.current:
            return
        try:
            frame = req.result()
        except Cancelled:
            return
        except Exception as e:  # noqa: BLE001 - shown in the slot
            self.slot.set_error(nid, e, self._failing_node(nid), req.generation)
            return
        self.slot.show(nid, frame, req.generation, self.session.summary(nid))

    def _failing_node(self, nid: str) -> str:
        """The most upstream step with an error for its current generation."""
        if nid not in self.session:
            return nid
        for node in self.session.ancestors(nid):  # parents first
            if self.session.error(node.id) is not None:
                return node.id
        return nid

    def _generation(self, nid: str) -> int | None:
        return self.session.generations((nid,)).get(nid)

    # --- bridge ------------------------------------------------------------------------
    def _on_removed(self, ids: tuple[str, ...]) -> None:
        current = self.state.current
        if current is None or current not in ids:
            return
        gone = set(ids)
        fallback = next(
            (a for a in reversed(self._lineage) if a not in gone and a in self.session), None
        )
        self.state.current = fallback

    def _on_moved(self, ids: tuple[str, ...]) -> None:
        """New parents (a middle step was deleted / restored): re-pin and new lineage."""
        current = self.state.current
        node = None if current is None else self.session.get(current)
        if node is None:
            return
        if current in ids:
            self.pins.set(SLOT, (node.id, *node.parents))
        self._lineage = tuple(a.id for a in self.session.ancestors(node.id) if a.id != node.id)

    def _on_invalidated(self, ids: tuple[str, ...]) -> None:
        current = self.state.current
        if current is None or current not in ids:
            return
        # the old frame is no longer cached: holding it would be an unbudgeted copy
        self._timer.stop()
        self._show_or_request(current, debounce=False, stale=True)

    def _on_evicted(self, ids: tuple[str, ...]) -> None:
        if self.slot.node_id in ids and self.slot.state == SlotState.READY:
            self.jobs.cancel(SLOT)
            self.slot.set_evicted()

    def _on_materialized(self, ids: tuple[str, ...]) -> None:
        current = self.state.current
        if current is None or current not in ids:
            return
        if self.slot.state in (SlotState.LOADING, SlotState.STALE, SlotState.EVICTED):
            self._timer.stop()
            if self._show_cached(current):
                self.jobs.cancel(SLOT)

    def _on_reset(self) -> None:
        stale_pins = [n for n in self.pins.pinned_ids() if n not in self.session]
        self.pins.forget(stale_pins)
        current = self.state.current
        if current is None:
            return
        if current not in self.session:
            self._on_removed((current,))
        elif self.slot.state == SlotState.READY and self.slot.generation != self._generation(
            current
        ):
            self._show_or_request(current, debounce=False, stale=True)
