"""Messages dock: user messages, failing steps and log records of the `datacook` loggers.

Sources: `app.message_posted` (`app.notify()`), `app.bridge.node_error` (the failing step)
and a `logging.Handler` on the `datacook` logger (records from any thread are forwarded to
the GUI thread through a queued Qt signal). The list keeps the last `MAX_ENTRIES`; a level
filter hides lower levels. Clicking a message that names a step selects it
(`app.state.current`).

`install()` also adds the language switch (View > Language, `application.set_language`).
"""

from dataclasses import dataclass, field
import datetime as dt
import logging
from typing import TYPE_CHECKING, Any, ClassVar

from prettyqt.qt import QtCore, QtGui, QtWidgets

from datacook.app.uimodules import DockSpec
from datacook.i18n import _


if TYPE_CHECKING:
    from datacook.app.controllers import AppController
    from datacook.app.controllers.app import Message
    from datacook.app.mainwindow import MainWindow


type Index = QtCore.QModelIndex | QtCore.QPersistentModelIndex

LOGGER_NAME = "datacook"
MAX_ENTRIES = 2000

LEVELS: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}
LEVEL_TITLES = {
    "debug": _("Debug"),
    "info": _("Info"),
    "warning": _("Warning"),
    "error": _("Error"),
}
LEVEL_COLORS_LIGHT = {
    "debug": "#6c757d",
    "info": "#1d70b8",
    "warning": "#b4690e",
    "error": "#c92a2a",
}
LEVEL_COLORS_DARK = {
    "debug": "#9aa0a6",
    "info": "#58a6ff",
    "warning": "#e3a008",
    "error": "#f87171",
}


def _level_color(level: str) -> str | None:
    pal = QtGui.QGuiApplication.palette()
    dark = pal.color(QtGui.QPalette.ColorRole.Base).lightness() < 128  # noqa: PLR2004
    return (LEVEL_COLORS_DARK if dark else LEVEL_COLORS_LIGHT).get(level)


@dataclass(frozen=True, slots=True)
class Entry:
    text: str
    level: str = "info"
    """debug | info | warning | error"""
    node_id: str | None = None
    source: str = "app"
    """app (notify) | step (node error) | log (logging record: `logger` is its name)"""
    logger: str = ""
    time: dt.datetime = field(default_factory=dt.datetime.now)

    @property
    def levelno(self) -> int:
        return LEVELS.get(self.level, logging.INFO)


def _level_name(levelno: int) -> str:
    if levelno >= logging.ERROR:
        return "error"
    if levelno >= logging.WARNING:
        return "warning"
    if levelno >= logging.INFO:
        return "info"
    return "debug"


class _LogRelay(QtCore.QObject):
    record = QtCore.Signal(object)


class QtLogHandler(logging.Handler):
    """Forwards log records (any thread) as `Entry`s to the GUI thread."""

    def __init__(self, relay: _LogRelay, level: int = logging.NOTSET) -> None:
        super().__init__(level)
        self.relay = relay

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = record.getMessage()
            if record.exc_info and record.exc_info[1] is not None:
                text = f"{text}: {record.exc_info[1]}"
            entry = Entry(
                text,
                _level_name(record.levelno),
                node_id=getattr(record, "node_id", None),
                source="log",
                logger=record.name,
            )
            self.relay.record.emit(entry)
        except RuntimeError:  # relay already deleted (shutdown)
            pass
        except Exception:  # noqa: BLE001
            self.handleError(record)


class MessageModel(QtCore.QAbstractTableModel):
    """Entries, oldest first; columns time, level, text."""

    HEADER: ClassVar = (_("Time"), _("Level"), _("Message"))

    def __init__(self, parent: QtCore.QObject | None = None, max_entries: int = MAX_ENTRIES):
        super().__init__(parent)
        self.entries: list[Entry] = []
        self.max_entries = max_entries

    def rowCount(self, parent: Index | None = None) -> int:  # noqa: N802
        return 0 if parent is not None and parent.isValid() else len(self.entries)

    def columnCount(self, parent: Index | None = None) -> int:  # noqa: N802
        return 0 if parent is not None and parent.isValid() else len(self.HEADER)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if (
            orientation == QtCore.Qt.Orientation.Horizontal
            and role == QtCore.Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(self.HEADER)
        ):
            return str(self.HEADER[section])
        return None

    def data(self, index: Index, /, role: int = QtCore.Qt.ItemDataRole.DisplayRole) -> Any:  # noqa: PLR0911
        if not index.isValid():
            return None
        entry = self.entries[index.row()]
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._display(entry, index.column())
        if role == QtCore.Qt.ItemDataRole.ForegroundRole:
            if index.column() == 1 and (color := _level_color(entry.level)):
                return QtGui.QBrush(QtGui.QColor(color))
            if index.column() == 0:
                return QtGui.QGuiApplication.palette().brush(
                    QtGui.QPalette.ColorRole.PlaceholderText
                )
        if role == QtCore.Qt.ItemDataRole.FontRole and index.column() == 1:
            font = QtGui.QFont()
            font.setBold(entry.level in ("warning", "error"))
            return font
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            return f"{entry.logger}: {entry.text}" if entry.logger else entry.text
        if role == QtCore.Qt.ItemDataRole.UserRole:
            return entry
        return None

    @staticmethod
    def _display(entry: Entry, column: int) -> str:
        match column:
            case 0:
                return entry.time.strftime("%H:%M:%S")
            case 1:
                return str(LEVEL_TITLES.get(entry.level, entry.level))
            case _:
                return entry.text

    def append(self, entry: Entry) -> None:
        if len(self.entries) >= self.max_entries:
            drop = len(self.entries) - self.max_entries + 1
            self.beginRemoveRows(QtCore.QModelIndex(), 0, drop - 1)
            del self.entries[:drop]
            self.endRemoveRows()
        row = len(self.entries)
        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        self.entries.append(entry)
        self.endInsertRows()

    def clear(self) -> None:
        self.beginResetModel()
        self.entries.clear()
        self.endResetModel()

    def retranslate(self) -> None:
        self.headerDataChanged.emit(QtCore.Qt.Orientation.Horizontal, 0, len(self.HEADER) - 1)
        if self.entries:
            self.dataChanged.emit(self.index(0, 1), self.index(len(self.entries) - 1, 1))


class LevelFilter(QtCore.QSortFilterProxyModel):
    """Hides entries below `min_level`."""

    def __init__(self, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self.min_level = logging.INFO

    def set_min_level(self, level: int) -> None:
        self.beginFilterChange()
        self.min_level = level
        self.endFilterChange(QtCore.QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(self, row: int, parent: Index, /) -> bool:  # noqa: N802
        source = self.sourceModel()
        assert isinstance(source, MessageModel)
        return source.entries[row].levelno >= self.min_level


class MessagesWidget(QtWidgets.QWidget):
    def __init__(self, app: AppController, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.app = app
        self.model = MessageModel(self)
        self.proxy = LevelFilter(self)
        self.proxy.setSourceModel(self.model)
        self.level_combo = QtWidgets.QComboBox()
        self.level_combo.setObjectName("message-level")
        for level in LEVELS:
            self.level_combo.addItem(str(LEVEL_TITLES[level]), level)
        self.level_combo.setCurrentIndex(list(LEVELS).index("info"))
        self.level_combo.currentIndexChanged.connect(self._on_level_changed)
        self.level_label = QtWidgets.QLabel()
        self.clear_button = QtWidgets.QPushButton()
        self.clear_button.setObjectName("message-clear")
        self.clear_button.clicked.connect(self.model.clear)
        self.view = QtWidgets.QTableView()
        self.view.setObjectName("message-list")
        self.view.setModel(self.proxy)
        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setAlternatingRowColors(True)
        self.view.setShowGrid(False)
        self.view.verticalHeader().hide()
        self.view.verticalHeader().setMinimumSectionSize(20)
        self.view.verticalHeader().setDefaultSectionSize(24)
        header = self.view.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.view.setWordWrap(False)
        self.view.clicked.connect(self._on_clicked)
        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(8, 6, 8, 4)
        bar.setSpacing(8)
        bar.addWidget(self.level_label)
        bar.addWidget(self.level_combo)
        bar.addStretch()
        bar.addWidget(self.clear_button)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(bar)
        layout.addWidget(self.view)

        app.message_posted.connect(self._on_message)
        app.bridge.node_error.connect(self._on_node_error)
        app.state.language_changed.connect(self.retranslate)
        self._relay = _LogRelay(self)
        self._relay.record.connect(self.add_entry)  # queued when emitted from a worker
        self.log_handler = QtLogHandler(self._relay)
        self._logger = logging.getLogger(LOGGER_NAME)
        self._logger.addHandler(self.log_handler)
        handler, logger = self.log_handler, self._logger
        self.destroyed.connect(lambda *_: logger.removeHandler(handler))
        app.destroyed.connect(lambda *_: logger.removeHandler(handler))
        self.retranslate()

    # --- sources -------------------------------------------------------------------------
    def add_entry(self, entry: Entry) -> None:
        self.model.append(entry)
        if entry.levelno >= self.proxy.min_level:
            self.view.scrollToBottom()

    def _on_message(self, message: Message) -> None:
        self.add_entry(Entry(message.text, message.level, message.node_id, source="app"))

    def _on_node_error(self, node_id: str, error: object) -> None:
        text = f"{self.node_label(node_id)}: {error}"
        self.add_entry(Entry(text, "error", node_id, source="step"))

    def node_label(self, node_id: str) -> str:
        node = self.app.session.get(node_id)
        if node is None:
            return node_id
        if node.name:
            return node.name
        try:
            return str(self.app.session.registry.get(node.op_id).title)
        except KeyError:
            return node.op_id

    # --- interaction ---------------------------------------------------------------------
    def entry_at(self, index: QtCore.QModelIndex) -> Entry | None:
        return self.proxy.data(index, QtCore.Qt.ItemDataRole.UserRole)

    def _on_clicked(self, index: QtCore.QModelIndex) -> None:
        entry = self.entry_at(index)
        if entry is not None and entry.node_id is not None and entry.node_id in self.app.session:
            self.app.state.current = entry.node_id

    def _on_level_changed(self, _index: int) -> None:
        self.proxy.set_min_level(LEVELS[self.level_combo.currentData()])

    def detach_log_handler(self) -> None:
        self._logger.removeHandler(self.log_handler)

    # --- i18n --------------------------------------------------------------------------
    def retranslate(self, _language: object = None) -> None:
        self.level_label.setText(str(_("Level:")))
        self.clear_button.setText(str(_("Clear")))
        for i, level in enumerate(LEVELS):
            self.level_combo.setItemText(i, str(LEVEL_TITLES[level]))
        self.model.retranslate()


def create(app: AppController, window: MainWindow) -> QtWidgets.QWidget:
    return MessagesWidget(app)


def install(app: AppController, window: MainWindow) -> None:
    """View > Language menu (the language switch lives in `application`)."""
    from datacook.app.application import add_language_menu

    add_language_menu(app, window)


DOCKS = (DockSpec("messages", _("Messages"), "bottom", create, tabify_with="code"),)
