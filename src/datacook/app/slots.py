"""ViewSlot: one long-lived frame holder per view ("current", "preview"; GUI thread only).

A slot owns a cutepandas `DataFrameHolder` for its whole lifetime: data views bind to
`slot.holder` once (`DataFrameViewer(holder)` / models sharing it) and never see another
holder. Controllers move the slot between `SlotState`s; every state change emits
`state_changed`, and every frame change goes through the holder (`about_to_change` /
`changed`).

Memory policy (design §5): the "current" slot holds the *cached* frame of a pinned node (no
extra bytes) or nothing; the "preview" slot holds a preview head only. `held_id` is the node
whose full frame the slot references (`None` for previews and empty slots).
"""

import enum
from typing import TYPE_CHECKING

from cutepandas.pandasmodels import DataFrameHolder
from prettyqt.qt import QtCore


if TYPE_CHECKING:
    from datacook.engine import FrameSummary
    from datacook.engine.frames import Frame


class SlotState(enum.StrEnum):
    EMPTY = "empty"
    """Nothing selected."""
    LOADING = "loading"
    """Computing ("computing…"; `summary` may give the last known shape)."""
    READY = "ready"
    """`holder.df` is the node's frame (or the preview head)."""
    STALE = "stale"
    """The shown node was invalidated; recomputing ("recomputing…", frame dropped)."""
    EVICTED = "evicted"
    """Frame dropped from memory ("Not in memory — Recompute"); no automatic re-request."""
    ERROR = "error"
    """`error` / `error_node` (may be an ancestor of `node_id`)."""


class ViewSlot(QtCore.QObject):
    state_changed = QtCore.Signal(str)
    """(SlotState) after every change of state, node or error."""

    def __init__(
        self, name: str, *, full_frames: bool = True, parent: QtCore.QObject | None = None
    ):
        super().__init__(parent)
        self.name = name
        self.full_frames = full_frames
        """True: holds full node frames (counts for `held_id`); False: preview heads."""
        self.holder = DataFrameHolder(parent=self)
        self.node_id: str | None = None
        self.generation: int | None = None
        self.state = SlotState.EMPTY
        self.summary: FrameSummary | None = None
        """Last known shape / schema (for the loading / stale overlay)."""
        self.error: BaseException | None = None
        self.error_node: str | None = None
        self.message: str = ""
        """Extra text for the overlay (e.g. "computing full result…")."""

    def __repr__(self) -> str:
        return f"ViewSlot({self.name!r}, {self.state}, node={self.node_id})"

    @property
    def frame(self) -> Frame | None:
        return self.holder.df

    @property
    def held_id(self) -> str | None:
        if self.full_frames and self.holder.df is not None:
            return self.node_id
        return None

    # --- transitions (controllers only) ------------------------------------------------
    def show(
        self,
        node_id: str | None,
        frame: Frame,
        generation: int | None = None,
        summary: FrameSummary | None = None,
    ) -> None:
        self._set(SlotState.READY, node_id, frame, generation=generation, summary=summary)

    def set_loading(
        self, node_id: str | None, summary: FrameSummary | None = None, message: str = ""
    ) -> None:
        self._set(SlotState.LOADING, node_id, None, summary=summary, message=message)

    def set_stale(self, summary: FrameSummary | None = None) -> None:
        self._set(SlotState.STALE, self.node_id, None, summary=summary or self.summary)

    def set_evicted(self) -> None:
        self._set(
            SlotState.EVICTED, self.node_id, None, generation=self.generation, summary=self.summary
        )

    def set_error(
        self,
        node_id: str | None,
        error: BaseException,
        error_node: str | None = None,
        generation: int | None = None,
    ) -> None:
        self._set(
            SlotState.ERROR,
            node_id,
            None,
            generation=generation,
            error=error,
            error_node=error_node,
        )

    def set_message(self, message: str) -> None:
        """Change the overlay text, keeping state and frame."""
        if message != self.message:
            self.message = message
            self.state_changed.emit(self.state.value)

    def clear(self) -> None:
        self._set(SlotState.EMPTY, None, None)

    def _set(
        self,
        state: SlotState,
        node_id: str | None,
        frame: Frame | None,
        *,
        generation: int | None = None,
        summary: FrameSummary | None = None,
        error: BaseException | None = None,
        error_node: str | None = None,
        message: str = "",
    ) -> None:
        self.state = state
        self.node_id = node_id
        self.generation = generation
        self.summary = summary
        self.error = error
        self.error_node = error_node
        self.message = message
        if frame is not None or self.holder.df is not None:
            self.holder.set_df(frame)
        self.state_changed.emit(state.value)
