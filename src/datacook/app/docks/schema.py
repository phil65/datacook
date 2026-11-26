"""Schema / column profile dock: the columns of the displayed frame and one column's stats.

- Shows the frame of the *displayed* slot (`app.state.display`: the current node or the
  preview). Each slot's holder gets its own `SchemaModel`, bound once; switching the display
  only swaps the model of the table.
- Selecting a row sets `app.state.column`; `column_changed` selects the row.
- Column statistics (`FrameSource.describe`: min / max / mean / unique / top values, a full
  column scan) run on the view pool (`app.jobs.submit_view`, slot "profile"). A newer
  request replaces the old job; a result that no longer matches the displayed frame and
  column is dropped.
- Categorical columns additionally list their categories (`CategoryModel`).
- Labels go through `datacook.i18n.translate` (cutepandas `translate=`), retranslated on
  `AppState.language_changed`.
"""

import functools
import logging
from typing import TYPE_CHECKING, Any

from cutepandas.frames import Kind
from cutepandas.pandasmodels import CategoryModel, SchemaModel
from cutepandas.pandaswidgets import ColumnProfileWidget
from prettyqt.qt import QtCore, QtWidgets

from datacook import i18n
from datacook.app.uimodules import DockSpec
from datacook.i18n import N_, _


if TYPE_CHECKING:
    import concurrent.futures

    from cutepandas.frames import ColumnInfo, ColumnStats, FrameSource
    from cutepandas.pandasmodels import DataFrameHolder

    from datacook.app.controllers import AppController
    from datacook.app.mainwindow import MainWindow
    from datacook.app.slots import ViewSlot


logger = logging.getLogger(__name__)

PROFILE_SLOT = "profile"
"""`JobRunner` slot of the column statistics job."""

TOP_VALUES = 10

# cutepandas labels, listed so that the gettext scan (`_`, `N_`) puts them in our catalog.
CUTEPANDAS_LABELS = (
    N_("Name"),
    N_("Type"),
    N_("Nulls"),
    N_("Size"),
    N_("Rows"),
    N_("Unique"),
    N_("Min"),
    N_("Max"),
    N_("Mean"),
    N_("Std"),
    N_("Value"),
    N_("Count"),
    N_("Share"),
    N_("Code"),
    N_("Items"),
)


def _describe(source: FrameSource, position: int) -> tuple[ColumnInfo, ColumnStats]:
    """View pool: statistics of one column (reads the frame only)."""
    return source.columns[position], source.describe(position, top=TOP_VALUES)


class SchemaWidget(QtWidgets.QWidget):
    """Columns table + profile of the selected column (+ categories if categorical)."""

    def __init__(self, app: AppController, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.app = app
        translate = i18n.translate
        self.models: dict[str, SchemaModel] = {
            "node": SchemaModel(app.nodes.slot.holder, translate=translate, parent=self),
            "preview": SchemaModel(app.preview.slot.holder, translate=translate, parent=self),
        }
        self.table = QtWidgets.QTableView()
        self.table.setObjectName("schema-table")
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.profile = ColumnProfileWidget(translate=translate)
        self.profile.setObjectName("column-profile")
        self.hint = QtWidgets.QLabel()
        self.hint.setObjectName("column-profile-hint")
        self.hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.hint.setWordWrap(True)
        self.hint.setEnabled(False)  # greyed out
        self.categories: CategoryModel | None = None
        """Categories of the profiled column (only for categorical columns)."""
        self.category_table = QtWidgets.QTableView()
        self.category_table.setObjectName("category-table")
        self.category_table.verticalHeader().hide()
        self.category_table.hide()
        lower = QtWidgets.QWidget()
        box = QtWidgets.QVBoxLayout(lower)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(self.hint)
        box.addWidget(self.profile)
        box.addWidget(self.category_table)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(lower)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self._display = ""
        self._epoch = 0
        """Counts changes of the displayed frame (display switch or new frame)."""
        self._stats_key: tuple[int, Any] | None = None
        """(epoch, column) of the requested / shown statistics."""
        self._selecting = False
        for name, model in self.models.items():
            model.holder.changed.connect(functools.partial(self._on_holder_changed, name))
        app.state.display_changed.connect(self._on_display_changed)
        app.state.column_changed.connect(self._on_column_changed)
        app.state.language_changed.connect(self.retranslate)
        self._on_display_changed(app.state.display)
        self.retranslate()

    # --- what is shown -----------------------------------------------------------------
    @property
    def slot(self) -> ViewSlot:
        return self.app.preview.slot if self._display == "preview" else self.app.nodes.slot

    @property
    def holder(self) -> DataFrameHolder:
        return self.slot.holder

    @property
    def model(self) -> SchemaModel:
        return self.models[self._display]

    def _on_display_changed(self, display: str) -> None:
        if display == self._display:
            return
        self._display = display
        old = self.table.selectionModel()
        self.table.setModel(self.model)
        if old is not None:
            old.deleteLater()
        self.table.selectionModel().currentRowChanged.connect(self._on_row_changed)
        self._epoch += 1
        self.refresh()

    def _on_holder_changed(self, name: str, _origin: object = None) -> None:
        if name == self._display:
            self._epoch += 1
            self.refresh()

    def _on_column_changed(self, _column: object) -> None:
        self.refresh()

    def refresh(self) -> None:
        """Select the row of `state.column` and (re)request its statistics."""
        position = self._position(self.app.state.column)
        self._select_row(position)
        source = self.holder.source
        self._show_hint(source is not None and position is None)
        if source is None or position is None:
            self._clear_profile()
            return
        info = source.columns[position]
        key = (self._epoch, info.name)
        if key == self._stats_key:
            return
        self._clear_profile()
        self._stats_key = key
        self.app.jobs.submit_view(
            PROFILE_SLOT,
            _describe,
            source,
            position,
            on_done=functools.partial(self._on_stats, key),
        )

    def _show_hint(self, show: bool) -> None:
        """No column selected: a hint instead of an empty profile."""
        self.hint.setVisible(show)
        self.profile.setVisible(not show)

    def _position(self, column: object) -> int | None:
        source = self.holder.source
        if source is None or column is None:
            return None
        for pos, info in enumerate(source.columns):
            if info.name == column:
                return pos
        return None

    def _select_row(self, position: int | None) -> None:
        selection = self.table.selectionModel()
        if selection is None:
            return
        self._selecting = True
        try:
            if position is None:
                selection.clearSelection()
                selection.setCurrentIndex(
                    QtCore.QModelIndex(), QtCore.QItemSelectionModel.SelectionFlag.NoUpdate
                )
            else:
                index = self.model.index(position, 0)
                flags = (
                    QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
                    | QtCore.QItemSelectionModel.SelectionFlag.Rows
                )
                selection.setCurrentIndex(index, flags)
                self.table.scrollTo(index)
        finally:
            self._selecting = False

    def _on_row_changed(self, current: QtCore.QModelIndex, _previous: object) -> None:
        if self._selecting or not current.isValid():
            return
        self.app.state.column = self.model.column(current.row()).name

    # --- statistics ----------------------------------------------------------------------
    def _clear_profile(self) -> None:
        if self._stats_key is not None:
            self.app.jobs.cancel(PROFILE_SLOT)
        self._stats_key = None
        self.profile.clear()
        self.category_table.hide()

    def _on_stats(self, key: tuple[int, Any], future: concurrent.futures.Future[Any]) -> None:
        """GUI thread: show the statistics if they still belong to what is displayed."""
        if key != self._stats_key:
            logger.debug("dropping stale column statistics for %r", key[1])
            return
        try:
            info, stats = future.result()
        except Exception as e:  # noqa: BLE001
            logger.warning("column statistics for %r failed: %s", key[1], e)
            return
        self.profile.set_stats(info, stats)
        self._show_categories(info)

    def _show_categories(self, info: ColumnInfo) -> None:
        old, self.categories = self.categories, None
        if info.kind == Kind.CATEGORICAL:
            # categories / counts: one value_counts scan of a categorical (codes), lazily
            self.categories = CategoryModel(
                self.holder, info.name, translate=i18n.translate, parent=self
            )
        self.category_table.setModel(self.categories)
        self.category_table.setVisible(self.categories is not None)
        if old is not None:
            old.deleteLater()

    # --- i18n --------------------------------------------------------------------------
    def retranslate(self, _language: object = None) -> None:
        for model in self.models.values():
            model.retranslate()
        if self.categories is not None:
            self.categories.retranslate()
        self.profile.retranslate()
        self.hint.setText(str(_("Select a column to see its statistics.")))


def create(app: AppController, window: MainWindow) -> QtWidgets.QWidget:
    return SchemaWidget(app)


DOCKS = (DockSpec("schema", _("Columns"), "right", create, tabify_with="params"),)
