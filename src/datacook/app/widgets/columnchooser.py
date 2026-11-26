"""Editors for the engine's column hints (`json_schema_extra={"widget": ...}`).

`PydanticForm` builds them through `widget_factories` (see `form_factories()`): each
editor offers the column names of one input frame (from `session.summary()`, so no frame is
held) and still accepts names that are not in the list (an input that is not computed yet,
or a column that only exists after an upstream edit). Every editor has `get_value()`,
`set_value()`, a `value_changed` signal and `set_columns(names)` to refresh the offered
names while keeping the value.

- `ColumnChooser` (`"column"`): one name, editable combo box.
- `ColumnsChooser` (`"columns"`): a list of names; checkable, drag to reorder.
- `ColumnMapEditor` (`"column_map"`): `{column: value}`, one row per column, empty value =
  not included; values are text, or JSON if the field's value type is not `str`.
- `CodeEditor` (`"code"`), `FileEdit` (`"file"`): text editors returning `str`.
"""

import json
from typing import TYPE_CHECKING, Any, get_args, get_origin

from prettyqt.qt import QtCore, QtGui, QtWidgets

from datacook.i18n import _


if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from pydantic.fields import FieldInfo


_ITEM_FLAGS = (
    QtCore.Qt.ItemFlag.ItemIsEnabled
    | QtCore.Qt.ItemFlag.ItemIsSelectable
    | QtCore.Qt.ItemFlag.ItemIsUserCheckable
    | QtCore.Qt.ItemFlag.ItemIsDragEnabled
)


class ColumnChooser(QtWidgets.QComboBox):
    """One column name: editable combo box over the input's columns."""

    value_changed = QtCore.Signal(object)

    def __init__(self, columns: Sequence[str] = (), parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self.set_columns(columns)
        self.setCurrentIndex(-1)
        self.editTextChanged.connect(lambda _text: self.value_changed.emit(self.get_value()))

    def columns(self) -> list[str]:
        return [self.itemText(i) for i in range(self.count())]

    def set_columns(self, columns: Iterable[str]) -> None:
        value = self.currentText()
        self.blockSignals(True)
        try:
            self.clear()
            self.addItems(list(columns))
            self.setEditText(value)
        finally:
            self.blockSignals(False)

    def get_value(self) -> str:
        return self.currentText()

    def set_value(self, value: str | None) -> None:
        self.setEditText("" if value is None else str(value))


class ColumnsChooser(QtWidgets.QListWidget):
    """A list of column names: check the wanted ones, drag them into order.

    Checked names come first, in the order of the value; names of the value that the input
    does not have (yet) are kept as checked items.
    """

    value_changed = QtCore.Signal(object)

    def __init__(self, columns: Sequence[str] = (), parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(QtCore.Qt.DropAction.MoveAction)
        self.setMaximumHeight(160)
        self._columns: list[str] = []
        self._loading = False
        self.itemChanged.connect(self._emit)
        self.model().rowsMoved.connect(self._emit)
        self.set_columns(columns)

    def _emit(self, *_args: object) -> None:
        if not self._loading:
            self.value_changed.emit(self.get_value())

    def columns(self) -> list[str]:
        return list(self._columns)

    def set_columns(self, columns: Iterable[str]) -> None:
        self._columns = list(columns)
        self._fill(self.get_value())

    def _fill(self, value: Sequence[str]) -> None:
        self._loading = True
        try:
            self.clear()
            names = [*value, *(c for c in self._columns if c not in value)]
            for name in dict.fromkeys(names):
                item = QtWidgets.QListWidgetItem(name)
                item.setFlags(_ITEM_FLAGS)
                checked = name in value
                state = QtCore.Qt.CheckState.Checked if checked else QtCore.Qt.CheckState.Unchecked
                item.setCheckState(state)
                if name not in self._columns:
                    item.setToolTip(str(_("Not a column of the input (yet)")))
                    item.setForeground(QtGui.QBrush(QtGui.QColor("#b26a00")))
                self.addItem(item)
        finally:
            self._loading = False

    def get_value(self) -> list[str]:
        items = (self.item(i) for i in range(self.count()))
        return [
            item.text()
            for item in items
            if item is not None and item.checkState() == QtCore.Qt.CheckState.Checked
        ]

    def set_value(self, value: Sequence[str] | None) -> None:
        self._fill(list(value or []))
        self._emit()


class ColumnMapEditor(QtWidgets.QTableWidget):
    """`{column: value}`: one row per input column; a row counts if its value is not empty.

    Names of the value that the input does not have are extra rows; the last row is a blank
    one for typing a new column name.
    """

    value_changed = QtCore.Signal(object)

    def __init__(
        self,
        columns: Sequence[str] = (),
        value_is_text: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(0, 2, parent)
        self._columns: list[str] = []
        self._text = value_is_text
        self._loading = False
        self.setHorizontalHeaderLabels([str(_("Column")), str(_("Value"))])
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().hide()
        self.setMinimumHeight(120)
        self.setMaximumHeight(220)
        self.itemChanged.connect(self._on_item_changed)
        self.set_columns(columns)

    def columns(self) -> list[str]:
        return list(self._columns)

    def set_columns(self, columns: Iterable[str]) -> None:
        self._columns = list(columns)
        self._fill(self._raw())

    def _raw(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for row in range(self.rowCount()):
            key, val = self.item(row, 0), self.item(row, 1)
            name = key.text().strip() if key is not None else ""
            text = val.text() if val is not None else ""
            if name and text.strip():
                result[name] = text
        return result

    def _fill(self, raw: Mapping[str, str]) -> None:
        self._loading = True
        try:
            names = list(dict.fromkeys([*self._columns, *raw]))
            self.setRowCount(0)
            for name in [*names, ""]:
                self._append_row(name, raw.get(name, ""))
        finally:
            self._loading = False

    def _append_row(self, name: str, text: str) -> None:
        row = self.rowCount()
        self.insertRow(row)
        key = QtWidgets.QTableWidgetItem(name)
        if name in self._columns:
            key.setFlags(key.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, 0, key)
        self.setItem(row, 1, QtWidgets.QTableWidgetItem(text))

    def _on_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        if self._loading:
            return
        last = self.rowCount() - 1
        key = self.item(last, 0)
        if item.row() == last and key is not None and key.text().strip():
            self._loading = True
            try:
                self._append_row("", "")
            finally:
                self._loading = False
        self.value_changed.emit(self.get_value())

    def _parse(self, text: str) -> Any:
        if self._text:
            return text
        try:
            return json.loads(text)
        except ValueError:
            return text

    def _format(self, value: Any) -> str:
        if self._text or isinstance(value, str):
            return str(value)
        return json.dumps(value)

    def get_value(self) -> dict[str, Any]:
        return {name: self._parse(text) for name, text in self._raw().items()}

    def set_value(self, value: Mapping[str, Any] | None) -> None:
        self._fill({str(k): self._format(v) for k, v in (value or {}).items()})
        self.value_changed.emit(self.get_value())


class CodeEditor(QtWidgets.QPlainTextEdit):
    """Python code (monospace)."""

    value_changed = QtCore.Signal(object)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
        self.setFont(font)
        self.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self.setMinimumHeight(140)
        self.textChanged.connect(lambda: self.value_changed.emit(self.get_value()))

    def get_value(self) -> str:
        return self.toPlainText()

    def set_value(self, value: str | None) -> None:
        if (value or "") != self.toPlainText():
            self.setPlainText(value or "")


class FileEdit(QtWidgets.QWidget):
    """A file path as text plus a "…" button (the reader `path` fields are `str`)."""

    value_changed = QtCore.Signal(object)

    def __init__(self, extensions: Sequence[str] = (), parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._extensions = tuple(extensions)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.line_edit = QtWidgets.QLineEdit()
        self.button = QtWidgets.QToolButton()
        self.button.setText("…")
        self.button.setToolTip(str(_("Choose a file")))
        layout.addWidget(self.line_edit, 1)
        layout.addWidget(self.button)
        self.line_edit.textChanged.connect(lambda _t: self.value_changed.emit(self.get_value()))
        self.button.clicked.connect(self._browse)

    def _browse(self) -> None:
        pattern = " ".join(f"*{ext}" for ext in self._extensions)
        filters = f"{pattern} ({pattern});;* (*)" if pattern else ""
        path, _filter = QtWidgets.QFileDialog.getOpenFileName(
            self, str(_("Choose a file")), self.get_value(), filters
        )
        if path:
            self.set_value(path)

    def get_value(self) -> str:
        return self.line_edit.text()

    def set_value(self, value: object) -> None:
        self.line_edit.setText("" if value is None else str(value))


# --- factories for PydanticForm ----------------------------------------------------------


type ColumnSource = Callable[[int], list[str]]
"""`columns(input_index) -> names` of an input frame (empty if unknown)."""

COLUMN_WIDGETS = ("column", "columns", "column_map")


def _value_is_text(info: FieldInfo) -> bool:
    """`dict[str, str]` fields keep values as text; anything else is parsed as JSON."""
    annotation = info.annotation
    if get_origin(annotation) is dict:
        args = get_args(annotation)
        return len(args) == 2 and args[1] is str  # noqa: PLR2004
    return False


def form_factories(
    columns: ColumnSource,
    extensions: Sequence[str] = (),
    created: list[QtWidgets.QWidget] | None = None,
) -> dict[str, Callable[[str, FieldInfo, Mapping[str, Any]], QtWidgets.QWidget]]:
    """`widget_factories` for `PydanticForm`: column choosers, code and file editors.

    Column editors are appended to `created` (to refresh their names later via
    `set_columns`); each carries its input index as the `column_input` property.
    """

    def track(widget: QtWidgets.QWidget, index: int) -> QtWidgets.QWidget:
        widget.setProperty("column_input", index)
        if created is not None:
            created.append(widget)
        return widget

    def column(_name: str, _info: FieldInfo, hints: Mapping[str, Any]) -> QtWidgets.QWidget:
        index = int(hints.get("input", 0))
        return track(ColumnChooser(columns(index)), index)

    def column_list(_name: str, _info: FieldInfo, hints: Mapping[str, Any]) -> QtWidgets.QWidget:
        index = int(hints.get("input", 0))
        return track(ColumnsChooser(columns(index)), index)

    def column_map(_name: str, info: FieldInfo, hints: Mapping[str, Any]) -> QtWidgets.QWidget:
        index = int(hints.get("input", 0))
        return track(ColumnMapEditor(columns(index), _value_is_text(info)), index)

    def code(_name: str, _info: FieldInfo, _hints: Mapping[str, Any]) -> QtWidgets.QWidget:
        return CodeEditor()

    def file(_name: str, _info: FieldInfo, hints: Mapping[str, Any]) -> QtWidgets.QWidget:
        return FileEdit(hints.get("extensions") or extensions)

    return {
        "column": column,
        "columns": column_list,
        "column_map": column_map,
        "code": code,
        "file": file,
    }
