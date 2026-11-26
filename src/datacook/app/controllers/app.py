"""AppController: owns the session, executors, bridge, state, jobs, pins and controllers.

This is the object every dock / widget gets (`create(app, window)`); see
`datacook/app/README.md` for what docks use.
"""

import concurrent.futures
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Literal

from prettyqt.qt import QtCore

from datacook import allocator
from datacook.app.bridge import SessionBridge
from datacook.app.controllers.command import CommandController
from datacook.app.controllers.node import NodeController
from datacook.app.controllers.preview import PreviewController
from datacook.app.jobs import JobRunner
from datacook.app.pins import PinBook
from datacook.app.state import AppState


if TYPE_CHECKING:
    from datacook.app.protocols import SessionLike
    from datacook.app.settings import AppSettings


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Message:
    """A user-facing message (messages dock); `node_id`: clicking it selects that step."""

    text: str
    level: Literal["info", "warning", "error"] = "info"
    node_id: str | None = None


class AppController(QtCore.QObject):
    jobs_changed = QtCore.Signal()
    """The set of running jobs changed (`jobs.running_ids()`, job indicator)."""
    message_posted = QtCore.Signal(object)
    """(Message) from `notify()`; node errors come from `bridge.node_error`."""

    def __init__(
        self,
        session: SessionLike | None = None,
        settings: AppSettings | None = None,
        parent: QtCore.QObject | None = None,
    ):
        super().__init__(parent)
        self.state = AppState(settings, self)
        settings = self.state.settings
        self._compute: concurrent.futures.ThreadPoolExecutor | None = None
        self._owns_session = session is None
        if session is None:
            from datacook.engine import Session

            self._compute = concurrent.futures.ThreadPoolExecutor(
                max_workers=settings.compute_threads, thread_name_prefix="datacook-compute"
            )
            session = Session(executor=self._compute, memory_budget=settings.memory_budget)
        self.session: SessionLike = session
        self.bridge = SessionBridge(session, self)
        self.pins = PinBook(session)
        # connected first: removed ids are unpinned before controllers react
        self.bridge.nodes_removed.connect(self.pins.forget)
        self.jobs = JobRunner(session, self.bridge.post, view_threads=settings.view_threads)
        self.jobs.add_listener(self.jobs_changed.emit)
        self.commands = CommandController(session, self)
        self.nodes = NodeController(session, self.state, self.bridge, self.jobs, self.pins, self)
        self.preview = PreviewController(
            session, self.state, self.bridge, self.jobs, self.pins, self.commands, self.nodes, self
        )
        self.state.settings_changed.connect(self._on_settings_changed)
        self._closed = False

    # --- memory ------------------------------------------------------------------------
    def held_ids(self) -> frozenset[str]:
        """Nodes whose full frame a view references (invariant: ⊆ `pins.pinned_ids()`)."""
        return self.nodes.held_ids()

    def free_memory(self) -> tuple[str, ...]:
        """Drop every cached frame that is not pinned; returns the dropped ids.

        Then returns freed allocator memory to the OS (`allocator.release`).
        """
        pinned = self.pins.pinned_ids()
        dropped = tuple(n for n in self.session.cached_ids() if n not in pinned)
        for nid in dropped:
            self.session.drop(nid)
        allocator.release()
        return dropped

    # --- messages ----------------------------------------------------------------------
    def notify(
        self,
        text: object,
        level: Literal["info", "warning", "error"] = "info",
        node_id: str | None = None,
    ) -> None:
        self.message_posted.emit(Message(str(text), level, node_id))

    # --- project -----------------------------------------------------------------------
    def new_project(self) -> None:
        """Empty tree, empty undo history."""
        self.preview.cancel()
        self.state.current = None
        for root in self.session.roots():
            if root.id in self.session:
                self.session.remove(root.id)
        self.commands.clear()
        self.commands.set_clean()
        # Deliver the removals now: a project load right after re-adds the same ids, and a
        # removal drained later would hit the re-added nodes (selection, pins, tree).
        self.bridge.flush()

    # --- lifecycle ---------------------------------------------------------------------
    def close(self) -> None:
        """Release every pin and job; shuts the session down if this controller made it."""
        if self._closed:
            return
        self._closed = True
        self.preview.close()
        self.state.current = None
        self.nodes.close()
        self.jobs.shutdown()
        self.pins.release_all()
        self.bridge.close()
        if self._owns_session:
            close = getattr(self.session, "close", None)
            if close is not None:
                close()
        if self._compute is not None:
            self._compute.shutdown(wait=False, cancel_futures=True)

    def _on_settings_changed(self, settings: AppSettings) -> None:
        if settings.memory_budget is not None and settings.memory_budget != (
            self.session.memory().budget
        ):
            self.session.set_memory_budget(settings.memory_budget)
