"""Data view (central): the current node's frame or the params preview, plus slot states.

Two cutepandas `DataFrameViewer`s, each bound once to a view slot's long-lived holder
(`app.nodes.slot.holder`, `app.preview.slot.holder`); `app.state.display` picks which one
is shown. The view never calls `set_df`: the controllers own the frames. Slot states other
than "ready" show an overlay ("computing…", "recomputing…", "Not in memory — Recompute",
errors with "Go to step").

Header click = display-only sort (design §12.1): the viewer only emits `sort_requested`
(`sortable=False`), the request becomes `app.state.sort`, and the row permutation (8 bytes
per row, no frame copy) is computed on the view pool (`app.jobs.submit_view`) and applied
on the GUI thread. Selecting another node resets it (AppState). The header context menu
offers "Add as sort step" (a real `sort_rows` node via `app.commands`). Scrolling
prefetches the next chunks on the view pool.
"""

from typing import TYPE_CHECKING, Any, cast

from cutepandas.pandaswidgets import DataFrameViewer
from prettyqt.qt import QtCore, QtWidgets

from datacook.app.docks.nodetree import node_label
from datacook.app.slots import SlotState
from datacook.app.state import SortSpec
from datacook.app.uimodules import DockSpec
from datacook.app.widgets.overlay import Overlay
from datacook.engine.ops import rows
from datacook.i18n import _


if TYPE_CHECKING:
    import concurrent.futures

    from cutepandas.pandasmodels import DataFrameModel
    from cutepandas.pandasmodels.dataframemodel import SortPermutation

    from datacook.app.controllers import AppController
    from datacook.app.mainwindow import MainWindow
    from datacook.app.slots import ViewSlot
    from datacook.app.state import Display


ASCENDING = QtCore.Qt.SortOrder.AscendingOrder
DESCENDING = QtCore.Qt.SortOrder.DescendingOrder
SORT_JOB = "sort"
PREFETCH_PAGE = 512
"""Rows prefetched beyond the visible ones."""


class SlotPage(QtWidgets.QWidget):
    """One viewer bound to a slot's holder, with the slot-state overlay."""

    def __init__(self, view: DataView, key: Display, slot: ViewSlot):
        super().__init__(view)
        self.data_view = view
        self.key = key
        self.slot = slot
        self.viewer = DataFrameViewer(slot.holder, sortable=False, sort_mode="permutation")
        self.viewer.setObjectName(f"viewer-{key}")
        model = self.model
        model.set_read_only(True)  # the frame is the cached one: never edit it in place
        model.set_color_values(view.app.state.settings.color_values)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.viewer)
        self.overlay = Overlay(self)
        self._prefetch_timer = QtCore.QTimer(self)
        self._prefetch_timer.setSingleShot(True)
        self._prefetch_timer.setInterval(30)
        self._prefetch_timer.timeout.connect(self.prefetch)
        table = self.viewer.table_data
        table.verticalScrollBar().valueChanged.connect(self._schedule_prefetch)
        slot.holder.changed.connect(self._schedule_prefetch)
        slot.state_changed.connect(self._on_state_changed)
        self.viewer.sort_requested.connect(self._on_sort_requested)
        table.selectionModel().currentChanged.connect(self._on_current_cell)
        header = self.viewer.table_columns
        header.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._on_header_menu)

    @property
    def model(self) -> DataFrameModel:
        return cast("DataFrameModel", self.viewer.table_data.get_model(skip_proxies=True))

    def column_name(self, position: int) -> str | None:
        columns = self.model.column_info
        if not 0 <= position < len(columns):
            return None
        return str(columns[position].name)

    def column_position(self, name: str) -> int | None:
        return next((i for i, c in enumerate(self.model.column_info) if str(c.name) == name), None)

    # --- prefetch ----------------------------------------------------------------------
    def prefetch(self) -> None:
        """Convert the visible rows plus one page ahead on the view pool."""
        model = self.model
        n_rows = model.rowCount()
        if self.slot.holder.df is None or n_rows == 0:
            return
        table = self.viewer.table_data
        first = max(table.rowAt(0), 0)
        last = table.rowAt(table.viewport().height())
        last = n_rows - 1 if last < 0 else last
        self.data_view.app.jobs.submit_view(
            f"prefetch-{self.key}",
            model.prefetch,
            first,
            min(last + PREFETCH_PAGE, n_rows - 1),
            on_done=lambda _f: None,
        )

    # --- signals (bound methods: disconnected when the page is destroyed) ---------------
    def _schedule_prefetch(self, *_args: object) -> None:
        self._prefetch_timer.start()

    def _on_state_changed(self, _state: str) -> None:
        self.data_view._on_slot_changed(self)

    def _on_sort_requested(self, position: int, order: Any) -> None:
        if (name := self.column_name(position)) is not None:
            self.data_view.app.state.sort = SortSpec(name, order == DESCENDING)

    def _on_current_cell(self, current: QtCore.QModelIndex, _previous: object) -> None:
        if current.isValid() and (name := self.column_name(current.column())) is not None:
            self.data_view.app.state.column = name

    def _on_header_menu(self, pos: QtCore.QPoint) -> None:
        header = self.viewer.table_columns
        name = self.column_name(header.indexAt(pos).column())
        if name is None:
            return
        menu = self.data_view.header_menu(name, self.key)
        menu.exec(header.viewport().mapToGlobal(pos))


class DataView(QtWidgets.QWidget):
    def __init__(self, app: AppController, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.app = app
        self.setObjectName("dataview")
        self.banner = QtWidgets.QLabel(self)
        self.banner.setObjectName("dataview-banner")
        self.banner.setVisible(False)
        self.stack = QtWidgets.QStackedWidget(self)
        self.pages: dict[Display, SlotPage] = {
            "node": SlotPage(self, "node", app.nodes.slot),
            "preview": SlotPage(self, "preview", app.preview.slot),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.banner)
        layout.addWidget(self.stack)
        self._sorting = False
        app.state.display_changed.connect(self._on_display_changed)
        app.state.sort_changed.connect(self._on_sort_changed)
        app.state.settings_changed.connect(self._on_settings_changed)
        app.state.language_changed.connect(self.retranslate)
        self._on_display_changed(app.state.display)

    # --- public ------------------------------------------------------------------------
    @property
    def page(self) -> SlotPage:
        """The displayed page (node or preview)."""
        return self.pages[self.app.state.display]

    @property
    def viewer(self) -> DataFrameViewer:
        return self.page.viewer

    def is_sorting(self) -> bool:
        return self._sorting

    def add_sort_step(self, column: str, descending: bool = False) -> str | None:
        """Add a real `sort_rows` step on the current node (undoable); selects it."""
        current = self.app.state.current
        if current is None or current not in self.app.session:
            return None
        record = rows.SortRows.record(by=[column], ascending=not descending)
        try:
            nid = self.app.commands.add_node(record, [current])
        except Exception as e:  # noqa: BLE001 - shown as a message
            self.app.notify(str(_("Could not add the sort step: {error}")).format(error=e), "error")
            return None
        self.app.state.current = nid
        return nid

    def header_menu(self, column: str, key: Display) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu(self)
        state = self.app.state
        asc = menu.addAction(str(_("Sort ascending (display only)")))
        asc.triggered.connect(lambda: setattr(state, "sort", SortSpec(column, False)))
        desc = menu.addAction(str(_("Sort descending (display only)")))
        desc.triggered.connect(lambda: setattr(state, "sort", SortSpec(column, True)))
        clear = menu.addAction(str(_("Clear display sort")))
        clear.setEnabled(state.sort is not None)
        clear.triggered.connect(lambda: setattr(state, "sort", None))
        menu.addSeparator()
        descending = (
            state.sort is not None and state.sort.column == column and (state.sort.descending)
        )
        step = menu.addAction(str(_("Add as sort step")))
        step.setObjectName("add-sort-step")
        step.setEnabled(key == "node" and state.current is not None)
        step.triggered.connect(lambda: self.add_sort_step(column, descending))
        return menu

    # --- display / overlay -------------------------------------------------------------
    def _on_display_changed(self, display: Display) -> None:
        self.stack.setCurrentWidget(self.pages[display])
        self.app.state.sort = None  # the sort belonged to the other frame
        self._update_overlay(self.pages[display])

    def _on_slot_changed(self, page: SlotPage) -> None:
        sort = self.app.state.sort
        if (
            page is self.page
            and sort is not None
            and page.slot.state == SlotState.READY
            and page.model.row_order is None
            and not self._sorting
        ):
            self._start_sort(sort)  # a new frame for the same node: sort it again
        self._update_overlay(page)

    def _update_overlay(self, page: SlotPage) -> None:
        if page is not self.page:
            return
        slot = page.slot
        overlay = page.overlay
        self._update_banner()
        match slot.state:
            case SlotState.READY:
                overlay.hide()
            case SlotState.EMPTY:
                if page.key == "node":
                    overlay.show_message(
                        str(_("No step selected")),
                        str(_("Open a data file or select a step in the tree.")),
                    )
                else:
                    overlay.show_message(str(_("No preview")))
            case SlotState.LOADING:
                overlay.show_message(str(_("Computing…")), self._shape_text(slot))
            case SlotState.STALE:
                overlay.show_message(str(_("Recomputing…")), self._shape_text(slot))
            case SlotState.EVICTED:
                overlay.show_message(
                    str(_("Not in memory")),
                    self._shape_text(slot),
                    [(str(_("Recompute")), self.app.nodes.recompute)],
                )
            case SlotState.ERROR:
                self._show_error(page)

    def _show_error(self, page: SlotPage) -> None:
        slot = page.slot
        failing = slot.error_node or slot.node_id
        name = node_label(self.app.session, failing) if failing else ""
        title = str(_("Step {name} failed")).format(name=name) if name else str(_("Failed"))
        buttons: list[tuple[str, Any]] = []
        if page.key == "node":
            if failing is not None and failing != slot.node_id:
                buttons.append((str(_("Go to step")), lambda: self._go_to(failing)))
            buttons.append((str(_("Retry")), self.app.nodes.recompute))
        page.overlay.show_message(title, str(slot.error or ""), buttons)

    def _go_to(self, nid: str) -> None:
        if nid in self.app.session:
            self.app.state.current = nid

    def _shape_text(self, slot: ViewSlot) -> str:
        parts = []
        if slot.summary is not None:
            parts.append(
                str(_("Last known shape: {rows:,} rows × {columns} columns")).format(  # noqa: RUF001
                    rows=slot.summary.n_rows, columns=slot.summary.n_columns
                )
            )
        if slot.message:
            parts.append(slot.message)
        return "\n".join(parts)

    def _update_banner(self) -> None:
        texts = []
        slot = self.page.slot
        if slot.state == SlotState.READY and slot.message:
            texts.append(slot.message)
        if self.page.key == "preview":
            texts.append(str(_("Preview (first rows)")))
        if self._sorting:
            texts.append(str(_("Sorting…")))
        elif (sort := self.app.state.sort) is not None and self.page.model.row_order is not None:
            arrow = "↓" if sort.descending else "↑"
            texts.append(
                str(_("Sorted by {column} {arrow} (display only)")).format(
                    column=sort.column, arrow=arrow
                )
            )
        self.banner.setText(" · ".join(texts))
        self.banner.setVisible(bool(texts))

    # --- display sort ------------------------------------------------------------------
    def _on_sort_changed(self, spec: SortSpec | None) -> None:
        self.app.jobs.cancel(SORT_JOB)
        self._sorting = False
        if spec is None:
            for page in self.pages.values():
                page.viewer.clear_sort()
            self._update_banner()
            return
        self._start_sort(spec)

    def _start_sort(self, spec: SortSpec) -> None:
        page = self.page
        position = page.column_position(spec.column)
        if position is None or page.slot.holder.df is None:
            self._update_banner()
            return
        order = DESCENDING if spec.descending else ASCENDING
        self._sorting = True
        self._update_banner()
        self.app.jobs.submit_view(
            SORT_JOB,
            page.model.compute_sort_permutation,
            position,
            order,
            on_done=lambda future: self._on_sorted(future, page, spec),
        )

    def _on_sorted(
        self,
        future: concurrent.futures.Future[SortPermutation | None],
        page: SlotPage,
        spec: SortSpec,
    ) -> None:
        self._sorting = False
        if self.app.state.sort != spec or page is not self.page:
            self._update_banner()
            return
        try:
            permutation = future.result()
        except Exception as e:  # noqa: BLE001 - shown as a message
            self.app.notify(str(_("Sorting failed: {error}")).format(error=e), "error")
            permutation = None
        if permutation is not None and page.model.apply_sort_permutation(permutation):
            order = DESCENDING if permutation.descending else ASCENDING
            page.viewer.set_sort_state(permutation.column, order)
        self._update_banner()

    # --- settings / language -----------------------------------------------------------
    def _on_settings_changed(self, settings: Any) -> None:
        for page in self.pages.values():
            if page.model.get_color_values() != settings.color_values:
                page.model.set_color_values(settings.color_values)

    def retranslate(self, _language: object = None) -> None:
        for page in self.pages.values():
            self._update_overlay(page)


def create(app: AppController, _window: MainWindow) -> QtWidgets.QWidget:
    return DataView(app)


DOCKS = (DockSpec("dataview", _("Data"), "central", create),)
