"""Memory indicator (status bar): `Cache x/y GB · RSS z GB`.

Refreshes on `bridge.memory_changed` and every 2 s (process RSS via psutil). Red when the
cache is over budget (pinned frames may exceed it; nothing is evicted then). Click: a menu
of the cached steps (size from `summary()`; choosing one selects it) and "Free memory"
(`app.free_memory()`: drops every unpinned cached frame).
"""

from typing import TYPE_CHECKING

from prettyqt.qt import QtCore, QtWidgets
import psutil

from datacook.app.docks.nodetree import format_bytes, node_label
from datacook.app.uimodules import DockSpec
from datacook.i18n import _


if TYPE_CHECKING:
    from datacook.app.controllers import AppController
    from datacook.app.mainwindow import MainWindow


GB = 1024**3
REFRESH_MS = 2000


def process_rss() -> int:
    return psutil.Process().memory_info().rss


class MemoryIndicator(QtWidgets.QToolButton):
    def __init__(self, app: AppController, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.app = app
        self.setObjectName("memory-indicator")
        self.setAutoRaise(True)
        self.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_ = QtWidgets.QMenu(self)
        self.menu_.aboutToShow.connect(self._fill_menu)
        self.setMenu(self.menu_)
        self.over_budget = False
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        app.bridge.memory_changed.connect(self.refresh)
        app.state.language_changed.connect(self.refresh)
        self.refresh()

    def refresh(self, *_args: object) -> None:
        stats = self.app.session.memory()
        rss = process_rss()
        self.over_budget = stats.used > stats.budget
        self.setText(
            str(_("Cache {used:.1f}/{budget:.1f} GB · RSS {rss:.1f} GB")).format(
                used=stats.used / GB, budget=stats.budget / GB, rss=rss / GB
            )
        )
        self.setToolTip(
            str(
                _(
                    "Frame cache: {used} of {budget}, {cached} steps in memory, {pinned} pinned"
                    "\nProcess memory (RSS): {rss}"
                )
            ).format(
                used=format_bytes(stats.used),
                budget=format_bytes(stats.budget),
                cached=stats.cached_nodes,
                pinned=stats.pinned_nodes,
                rss=format_bytes(rss),
            )
        )
        self.setStyleSheet("color: #dc322f;" if self.over_budget else "")

    def cached_entries(self) -> list[tuple[str, str, int | None]]:
        """(node id, label, size in bytes or None) of the cached steps, largest first."""
        session = self.app.session
        entries = []
        for nid in session.cached_ids():
            if nid not in session:
                continue
            summary = session.summary(nid)
            entries.append((
                nid,
                node_label(session, nid),
                None if summary is None else summary.nbytes,
            ))
        return sorted(entries, key=lambda e: -(e[2] or 0))

    def _fill_menu(self) -> None:
        menu = self.menu_
        menu.clear()
        entries = self.cached_entries()
        pinned = self.app.pins.pinned_ids()
        header = menu.addAction(str(_("Steps in memory")))
        header.setEnabled(False)
        if not entries:
            empty = menu.addAction(str(_("(none)")))
            empty.setEnabled(False)
        for nid, label, size in entries:
            text = label if size is None else f"{label}  ({format_bytes(size)})"
            if nid in pinned:
                text += "  " + str(_("[pinned]"))
            action = menu.addAction(text)
            action.triggered.connect(lambda _c=False, n=nid: self._select(n))
        menu.addSeparator()
        free = menu.addAction(str(_("Free memory")))
        free.setObjectName("free-memory")
        free.triggered.connect(self.free_memory)

    def _select(self, nid: str) -> None:
        if nid in self.app.session:
            self.app.state.current = nid

    def free_memory(self) -> tuple[str, ...]:
        dropped = self.app.free_memory()
        self.app.notify(
            str(_("Freed {n} cached steps")).format(n=len(dropped))
            if dropped
            else str(_("Nothing to free: only steps in use are in memory")),
        )
        self.refresh()
        return dropped


def create(app: AppController, _window: MainWindow) -> QtWidgets.QWidget:
    return MemoryIndicator(app)


DOCKS = (DockSpec("memory", _("Memory"), "status", create),)
