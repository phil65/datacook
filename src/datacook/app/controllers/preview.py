"""PreviewController: params form with live preview, then commit (GUI thread only).

Flow (design §3): `start_add` / `start_edit` open a `PreviewSpec` in `AppState.preview` and
pin the inputs. The params form calls `set_params` (it debounces itself); one preview job
runs at a time in the "preview" job slot, edits during a running job replace the pending
params ("latest wins"), and the pending params start when the job ends. A result goes to
the preview slot (a head of `settings.preview_rows` rows) and `AppState.display` becomes
"preview". `commit()` pushes `EditParamsCommand` / `AddNodeCommand`; the preview head stays
on screen ("computing full result…") until the current slot shows the committed result of
the current generation, then the display goes back to "node" and the preview closes.

Edits of the inputs (undo, an ancestor's params, code) re-run the preview; a changed target
(edit mode, e.g. undo) reloads the spec's params from the session (the form follows
`preview_changed`); removal of the target or an input closes the preview.
"""

import dataclasses
from typing import TYPE_CHECKING

from prettyqt.qt import QtCore

from datacook.app.slots import SlotState, ViewSlot
from datacook.app.state import PreviewSpec
from datacook.engine import Cancelled, OpRecord
from datacook.i18n import _


if TYPE_CHECKING:
    from collections.abc import Sequence

    from datacook.app.bridge import SessionBridge
    from datacook.app.controllers.command import CommandController
    from datacook.app.controllers.node import NodeController
    from datacook.app.jobs import JobRunner
    from datacook.app.pins import PinBook
    from datacook.app.protocols import RequestLike, SessionLike
    from datacook.app.state import AppState
    from datacook.engine import Params


SLOT = "preview"


class PreviewController(QtCore.QObject):
    committed = QtCore.Signal(str)
    """(node id) a commit finished (the current slot shows its result or error)."""

    def __init__(
        self,
        session: SessionLike,
        state: AppState,
        bridge: SessionBridge,
        jobs: JobRunner,
        pins: PinBook,
        commands: CommandController,
        nodes: NodeController,
        parent: QtCore.QObject | None = None,
    ):
        super().__init__(parent)
        self.session = session
        self.state = state
        self.jobs = jobs
        self.pins = pins
        self.commands = commands
        self.nodes = nodes
        self.slot = ViewSlot(SLOT, full_frames=False, parent=self)
        self._requested: Params | None = None
        self._pending: Params | None = None
        self._awaiting: str | None = None
        """Node id whose full result ends a commit."""
        self._base: Params | None = None
        """Edit mode: the target's committed params (to notice outside changes)."""
        bridge.nodes_removed.connect(self._on_removed)
        bridge.nodes_invalidated.connect(self._on_invalidated)
        bridge.nodes_changed.connect(self._on_changed)
        nodes.slot.state_changed.connect(self._check_commit)

    @property
    def spec(self) -> PreviewSpec | None:
        return self.state.preview

    @property
    def committing(self) -> bool:
        return self._awaiting is not None

    # --- public ------------------------------------------------------------------------
    def start_add(
        self, op_id: str, inputs: Sequence[str] = (), params: Params | None = None
    ) -> PreviewSpec:
        """Open a preview for a new step of `op_id` on `inputs` (none for readers)."""
        inputs = tuple(inputs)
        spec = PreviewSpec("add", op_id, inputs[0] if inputs else None, inputs)
        return self._start(spec, params)

    def start_edit(self, node_id: str) -> PreviewSpec:
        """Open a preview for new params of an existing step (starts from its params)."""
        node = self.session.get(node_id)
        if node is None:
            raise KeyError(node_id)
        spec = PreviewSpec("edit", node.op_id, node_id, node.parents)
        spec = self._start(spec, node.record.params)
        self._base = node.record.params
        return spec

    def set_params(self, params: Params | None) -> None:
        """New form values (`None`: invalid input, nothing to preview)."""
        spec = self.spec
        if spec is None or self.committing:
            return
        self.state.preview = dataclasses.replace(spec, params=params)
        if params is None or params == self._requested:
            self._pending = None
            return
        if self.jobs.is_running(SLOT):
            self._pending = params  # latest wins, no queue
            return
        self._run(params)

    def commit(self) -> str | None:
        """Apply (edit) / Add; returns the node id or None if there is nothing to commit."""
        spec = self.spec
        if spec is None or self.committing:
            return None
        params = spec.params or self._requested
        if params is None:
            return None
        record = OpRecord(spec.op_id, params)
        self.jobs.cancel(SLOT)
        self._pending = None
        if spec.mode == "edit":
            assert spec.target is not None
            self.commands.edit_params(spec.target, record)
            node_id = spec.target
            if self.state.current not in (node_id, *self.session.descendants(node_id)):
                self._finish_commit(node_id)
                return node_id
        else:
            node_id = self.commands.add_node(record, spec.inputs)
            self.state.current = node_id
        self._awaiting = self.state.current
        if self.slot.frame is not None:
            self.slot.set_message(str(_("computing full result…")))
        else:
            self.state.display = "node"
        self._check_commit()
        return node_id

    def cancel(self) -> None:
        """Close the preview without committing."""
        self.jobs.cancel(SLOT)
        self.pins.release(SLOT)
        self.slot.clear()
        self._requested = self._pending = self._awaiting = self._base = None
        self.state.preview = None
        self.state.display = "node"

    def close(self) -> None:
        self.cancel()

    # --- flow --------------------------------------------------------------------------
    def _start(self, spec: PreviewSpec, params: Params | None) -> PreviewSpec:
        self.cancel()
        self.pins.set(SLOT, spec.inputs)
        self.state.preview = spec
        if params is not None:
            self.set_params(params)
        return self.state.preview or spec

    def _run(self, params: Params) -> None:
        spec = self.spec
        if spec is None:
            return
        self._requested = params
        self._pending = None
        if self.slot.frame is None:
            self.slot.set_loading(None)
        else:
            self.slot.set_message(str(_("updating…")))
        record = OpRecord(spec.op_id, params)
        rows = self.state.settings.preview_rows
        self.jobs.request_evaluate(SLOT, record, spec.inputs, self._on_done, head=rows)

    def _on_done(self, req: RequestLike) -> None:
        if self.spec is None or self.committing:
            return
        try:
            frame = req.result()
        except Cancelled:
            return
        except Exception as e:  # noqa: BLE001 - shown in the slot
            self.slot.set_error(None, e)
        else:
            self.slot.show(None, frame)
        self.state.display = "preview"
        if self._pending is not None and self._pending != self._requested:
            self._run(self._pending)

    def _rerun(self) -> None:
        spec = self.spec
        params = spec.params if spec is not None and spec.params is not None else self._requested
        self.jobs.cancel(SLOT)
        self._requested = None
        if params is not None:
            self._run(params)

    def _check_commit(self, _state: str | None = None) -> None:
        awaiting = self._awaiting
        if awaiting is None:
            return
        slot = self.nodes.slot
        if awaiting != self.state.current:
            self._finish_commit(awaiting)
            return
        gen = self.session.generations((awaiting,)).get(awaiting)
        if (
            slot.node_id == awaiting
            and slot.state in (SlotState.READY, SlotState.ERROR, SlotState.EVICTED)
            and slot.generation == gen
        ):
            self._finish_commit(awaiting)

    def _finish_commit(self, node_id: str) -> None:
        self._awaiting = None
        self.cancel()
        self.committed.emit(node_id)

    # --- bridge ------------------------------------------------------------------------
    def _on_removed(self, ids: tuple[str, ...]) -> None:
        spec = self.spec
        if spec is None:
            return
        involved = {n for n in (spec.target, *spec.inputs) if n is not None}
        if self._awaiting in ids or (not self.committing and involved.intersection(ids)):
            self.cancel()

    def _on_invalidated(self, ids: tuple[str, ...]) -> None:
        spec = self.spec
        if spec is None or self.committing:
            return
        if set(spec.inputs) & set(ids):
            self._rerun()

    def _on_changed(self, ids: tuple[str, ...]) -> None:
        spec = self.spec
        if spec is None or self.committing or spec.mode != "edit" or spec.target not in ids:
            return
        assert spec.target is not None
        node = self.session.get(spec.target)
        if node is None or node.record.params == self._base:
            return  # name / comment only
        # the step was changed from outside (undo, code): the form reloads from the spec
        self._base = node.record.params
        self.state.preview = dataclasses.replace(spec, params=node.record.params)
        self._rerun()
