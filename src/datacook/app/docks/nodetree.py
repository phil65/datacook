"""Node tree dock: the step tree with status badges, shape and size (left).

`NodeTreeModel` stores ids and structure only; every `data()` call reads the session
(`get`, `summary`, `error`, `is_cached`: lock-protected and cheap). A node with several
parents (merge, concat) is shown under its first parent. Selecting a row writes
`app.state.current`; rename / comment / delete go through `app.commands` (undoable);
"Branch from here" selects the node, so the next added step becomes a child (a branch if
the node already has children).
"""

import enum
from typing import TYPE_CHECKING, Any

from prettyqt.qt import QtCore, QtGui, QtWidgets

from datacook.app.uimodules import DockSpec
from datacook.i18n import _


if TYPE_CHECKING:
    from collections.abc import Iterable

    from datacook.app.controllers import AppController
    from datacook.app.mainwindow import MainWindow
    from datacook.app.protocols import SessionLike


NODE_ID_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1
STATUS_ROLE = QtCore.Qt.ItemDataRole.UserRole + 2


class NodeStatus(enum.StrEnum):
    ERROR = "error"
    COMPUTING = "computing"
    PINNED = "pinned"
    IN_MEMORY = "in memory"
    NOT_COMPUTED = "not computed"


STATUS_TEXT = {
    NodeStatus.ERROR: _("Error"),
    NodeStatus.COMPUTING: _("Computing"),
    NodeStatus.PINNED: _("Pinned (in use)"),
    NodeStatus.IN_MEMORY: _("In memory"),
    NodeStatus.NOT_COMPUTED: _("Not computed"),
}

STATUS_COLORS = {
    NodeStatus.ERROR: "#dc322f",
    NodeStatus.COMPUTING: "#e6a000",
    NodeStatus.PINNED: "#268bd2",
    NodeStatus.IN_MEMORY: "#2aa14f",
    NodeStatus.NOT_COMPUTED: "#a0a0a0",
}

type Index = QtCore.QModelIndex | QtCore.QPersistentModelIndex
_ROOT = QtCore.QModelIndex()
SHAPE = "{rows:,} \u00d7 {columns}"
KB = 1024

HEADERS = (_("Step"), _("Shape"), _("Size"))


def format_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < KB or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= KB
    return f"{size:.1f} GB"  # pragma: no cover


def node_label(session: SessionLike, nid: str) -> str:
    """Name of a step, else its (translated) op title."""
    node = session.get(nid)
    if node is None:
        return nid
    if node.name:
        return node.name
    try:
        return str(session.registry.get(node.op_id).title)
    except KeyError:
        return node.op_id


_ICONS: dict[NodeStatus, QtGui.QIcon] = {}


def status_icon(status: NodeStatus) -> QtGui.QIcon:
    """A coloured dot (no icon font needed); cached per status."""
    if status not in _ICONS:
        pixmap = QtGui.QPixmap(12, 12)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(STATUS_COLORS[status]))
        if status == NodeStatus.NOT_COMPUTED:
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor(STATUS_COLORS[status]), 1.5))
        painter.drawEllipse(2, 2, 8, 8)
        painter.end()
        _ICONS[status] = QtGui.QIcon(pixmap)
    return _ICONS[status]


class NodeTreeModel(QtCore.QAbstractItemModel):
    """Tree of node ids (structure only); data is read from the session on demand."""

    def __init__(self, app: AppController, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self.app = app
        self.session = app.session
        self._children: dict[str | None, list[str]] = {None: []}
        self._parent: dict[str, str | None] = {}
        self._keys: dict[str, int] = {}
        self._ids: dict[int, str] = {}
        self._next_key = 1
        self._badged: frozenset[str] = frozenset()
        """Nodes shown as pinned / computing at the last refresh (to repaint changes)."""
        bridge = app.bridge
        bridge.nodes_added.connect(self._on_added)
        bridge.nodes_removed.connect(self._on_removed)
        bridge.nodes_changed.connect(self.refresh_ids)
        bridge.nodes_moved.connect(self._on_moved)
        bridge.nodes_invalidated.connect(self.refresh_ids)
        bridge.nodes_materialized.connect(self.refresh_ids)
        bridge.nodes_evicted.connect(self.refresh_ids)
        bridge.node_error.connect(self._on_error)
        bridge.structure_reset.connect(self.rebuild)
        app.jobs_changed.connect(self.refresh_badges)
        app.state.current_changed.connect(self.refresh_badges)
        app.state.preview_changed.connect(self.refresh_badges)
        app.state.language_changed.connect(self._on_language)
        self.rebuild()

    # --- structure ---------------------------------------------------------------------
    def rebuild(self) -> None:
        self.beginResetModel()
        self._children = {None: []}
        self._parent = {}
        for node in self.session.nodes():  # parents first
            self._attach(node.id, node.parents[0] if node.parents else None)
        self._badged = self._badge_ids()
        self.endResetModel()

    def _attach(self, nid: str, parent: str | None) -> None:
        if parent is not None and parent not in self._parent:
            parent = None  # parent not shown (should not happen): show as a root
        self._parent[nid] = parent
        self._children.setdefault(parent, []).append(nid)
        self._children.setdefault(nid, [])
        if nid not in self._keys:
            self._keys[nid] = self._next_key
            self._ids[self._next_key] = nid
            self._next_key += 1

    def _on_added(self, ids: tuple[str, ...]) -> None:
        for nid in ids:
            node = self.session.get(nid)
            if node is None or nid in self._parent:
                continue
            parent = node.parents[0] if node.parents else None
            if parent is not None and parent not in self._parent:
                parent = None
            siblings = self._children.setdefault(parent, [])
            row = len(siblings)
            self.beginInsertRows(self.index_of(parent), row, row)
            self._attach(nid, parent)
            self.endInsertRows()

    def _on_removed(self, ids: tuple[str, ...]) -> None:
        gone = {nid for nid in ids if nid in self._parent}
        # remove the top-most removed nodes; their subtrees go with them
        for nid in [n for n in ids if n in gone and self._parent.get(n) not in gone]:
            if nid not in self._parent:
                continue
            parent = self._parent[nid]
            row = self._children[parent].index(nid)
            self.beginRemoveRows(self.index_of(parent), row, row)
            self._children[parent].pop(row)
            self._forget(nid)
            self.endRemoveRows()

    def _on_moved(self, ids: tuple[str, ...]) -> None:
        """Re-parented nodes move (with their subtrees) to the end of the new parent's rows."""
        for nid in ids:
            node = self.session.get(nid)
            if node is None or nid not in self._parent:
                continue
            new = node.parents[0] if node.parents else None
            if new is not None and new not in self._parent:
                new = None
            old = self._parent[nid]
            if old == new:
                continue
            row = self._children[old].index(nid)
            dest = len(self._children.setdefault(new, []))
            if not self.beginMoveRows(self.index_of(old), row, row, self.index_of(new), dest):
                self.rebuild()  # pragma: no cover - Qt refuses only invalid moves
                return
            self._children[old].pop(row)
            self._children[new].append(nid)
            self._parent[nid] = new
            self.endMoveRows()

    def _forget(self, nid: str) -> None:
        for child in self._children.pop(nid, []):
            self._forget(child)
        self._parent.pop(nid, None)
        key = self._keys.pop(nid, None)
        if key is not None:
            self._ids.pop(key, None)

    # --- repaint -----------------------------------------------------------------------
    def refresh_ids(self, ids: Iterable[str]) -> None:
        last = self.columnCount() - 1
        for nid in ids:
            if nid in self._parent:
                index = self.index_of(nid)
                self.dataChanged.emit(index, index.siblingAtColumn(last))

    def _on_error(self, nid: str, _exc: object) -> None:
        # descendants show "upstream error" in their tooltip
        self.refresh_ids((nid, *self.session.descendants(nid)))

    def _badge_ids(self) -> frozenset[str]:
        return self.app.pins.pinned_ids() | self.app.jobs.running_ids()

    def refresh_badges(self, *_args: object) -> None:
        badged = self._badge_ids()
        changed = badged ^ self._badged
        self._badged = badged
        self.refresh_ids(changed)

    def _on_language(self, _language: object) -> None:
        self.headerDataChanged.emit(QtCore.Qt.Orientation.Horizontal, 0, len(HEADERS) - 1)
        self.refresh_ids(list(self._parent))

    # --- lookups -----------------------------------------------------------------------
    def node_id(self, index: Index) -> str | None:
        if not index.isValid():
            return None
        return self._ids.get(index.internalId())

    def index_of(self, nid: str | None, column: int = 0) -> QtCore.QModelIndex:
        if nid is None or nid not in self._parent:
            return QtCore.QModelIndex()
        parent = self._parent[nid]
        row = self._children[parent].index(nid)
        return self.createIndex(row, column, self._keys[nid])

    def ids(self) -> list[str]:
        """Shown node ids, depth first (tests, text snapshots)."""
        out: list[str] = []

        def visit(parent: str | None) -> None:
            for child in self._children.get(parent, []):
                out.append(child)
                visit(child)

        visit(None)
        return out

    def depth(self, nid: str) -> int:
        depth = 0
        while (parent := self._parent.get(nid)) is not None:
            depth += 1
            nid = parent
        return depth

    def status(self, nid: str) -> NodeStatus:
        if self.session.error(nid) is not None:
            return NodeStatus.ERROR
        if nid in self.app.jobs.running_ids():
            return NodeStatus.COMPUTING
        if nid in self.app.pins.pinned_ids() and self.session.is_cached(nid):
            return NodeStatus.PINNED
        if self.session.is_cached(nid):
            return NodeStatus.IN_MEMORY
        return NodeStatus.NOT_COMPUTED

    def label(self, nid: str) -> str:
        return node_label(self.session, nid)

    def _upstream_error(self, nid: str) -> str | None:
        for node in self.session.ancestors(nid):
            if node.id != nid and self.session.error(node.id) is not None:
                return self.label(node.id)
        return None

    def _tooltip(self, nid: str) -> str:
        node = self.session.get(nid)
        status = self.status(nid)
        lines = [self.label(nid), str(STATUS_TEXT[status])]
        if status == NodeStatus.ERROR:
            lines.append(str(self.session.error(nid)))
        elif (upstream := self._upstream_error(nid)) is not None:
            lines.append(str(_("Upstream error in step {name}")).format(name=upstream))
        if node is not None and node.comment:
            lines.append(node.comment)
        return "\n".join(lines)

    # --- Qt model API ------------------------------------------------------------------
    def index(self, row: int, column: int, parent: Index = _ROOT) -> QtCore.QModelIndex:
        children = self._children.get(self.node_id(parent), [])
        if not 0 <= row < len(children) or not 0 <= column < len(HEADERS):
            return QtCore.QModelIndex()
        return self.createIndex(row, column, self._keys[children[row]])

    def parent(self, index: Index = _ROOT) -> QtCore.QModelIndex:  # ty: ignore[incompatible-method-override]
        nid = self.node_id(index)
        if nid is None:
            return QtCore.QModelIndex()
        return self.index_of(self._parent.get(nid))

    def rowCount(self, parent: Index = _ROOT) -> int:  # noqa: N802
        if parent.isValid() and parent.column() != 0:
            return 0
        return len(self._children.get(self.node_id(parent), []))

    def columnCount(self, parent: Index = _ROOT) -> int:  # noqa: N802
        return len(HEADERS)

    def headerData(  # noqa: N802
        self, section: int, orientation: QtCore.Qt.Orientation, role: int = 0
    ) -> Any:
        if (
            orientation == QtCore.Qt.Orientation.Horizontal
            and role == QtCore.Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(HEADERS)
        ):
            return str(HEADERS[section])
        return None

    def flags(self, index: Index) -> QtCore.Qt.ItemFlag:
        flags = super().flags(index)
        if index.isValid() and index.column() == 0:
            flags |= QtCore.Qt.ItemFlag.ItemIsEditable
        return flags

    def data(self, index: Index, role: int = 0) -> Any:  # noqa: PLR0911
        nid = self.node_id(index)
        if nid is None:
            return None
        col = index.column()
        match role:
            case QtCore.Qt.ItemDataRole.DisplayRole:
                if col == 0:
                    return self.label(nid)
                summary = self.session.summary(nid)
                if summary is None:
                    return ""
                if col == 1:
                    return SHAPE.format(rows=summary.n_rows, columns=summary.n_columns)
                return format_bytes(summary.nbytes)
            case QtCore.Qt.ItemDataRole.EditRole if col == 0:
                return self.label(nid)
            case QtCore.Qt.ItemDataRole.DecorationRole if col == 0:
                return status_icon(self.status(nid))
            case QtCore.Qt.ItemDataRole.ToolTipRole:
                return self._tooltip(nid)
            case QtCore.Qt.ItemDataRole.TextAlignmentRole if col > 0:
                return int(
                    QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
                )
            case QtCore.Qt.ItemDataRole.ForegroundRole if col > 0:
                return QtGui.QGuiApplication.palette().brush(
                    QtGui.QPalette.ColorRole.PlaceholderText
                )
            case QtCore.Qt.ItemDataRole.FontRole if col == 0:
                node = self.session.get(nid)
                if node is not None and node.comment:
                    font = QtGui.QFont()
                    font.setItalic(True)
                    return font
            case _ if role == NODE_ID_ROLE:
                return nid
            case _ if role == STATUS_ROLE:
                return self.status(nid).value
        return None

    def setData(self, index: Index, value: Any, role: int = 2) -> bool:  # noqa: N802
        nid = self.node_id(index)
        if nid is None or role != QtCore.Qt.ItemDataRole.EditRole or index.column() != 0:
            return False
        name = str(value).strip()
        if not name or name == self.label(nid):
            return False
        try:
            self.app.commands.rename(nid, name)
        except Exception as e:  # noqa: BLE001 - shown as a message
            self.app.notify(str(_("Rename failed: {error}")).format(error=e), "error", nid)
            return False
        return True


class NodeTreeWidget(QtWidgets.QWidget):
    """Tree view over `NodeTreeModel`, synced with `app.state.current`."""

    def __init__(self, app: AppController, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.app = app
        self.model = NodeTreeModel(app, self)
        self.view = QtWidgets.QTreeView(self)
        self.view.setObjectName("node-tree")
        self.view.setModel(self.model)
        self.view.setUniformRowHeights(True)
        self.view.setAlternatingRowColors(True)
        self.view.setIndentation(14)
        self.view.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed
            | QtWidgets.QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.view.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context_menu)
        header = self.view.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self._syncing = False
        self.view.selectionModel().currentRowChanged.connect(self._on_row_changed)
        app.state.current_changed.connect(self._on_current_changed)
        self.model.rowsInserted.connect(self._on_rows_inserted)
        self.model.modelReset.connect(lambda: self._on_current_changed(None, app.state.current))
        self.extra_actions: list[QtGui.QAction] = []
        """More context menu entries (other modules append, e.g. "Save as recipe")."""
        self._make_actions()
        app.state.language_changed.connect(self.retranslate)

    # --- actions -----------------------------------------------------------------------
    def _make_actions(self) -> None:
        def action(text: object, slot: Any, shortcut: str | None = None) -> QtGui.QAction:
            act = QtGui.QAction(str(text), self)
            act.setProperty("msgid", text)
            act.triggered.connect(slot)
            if shortcut:
                act.setShortcut(shortcut)
                act.setShortcutContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
                self.view.addAction(act)
            return act

        self.rename_action = action(_("Rename"), self._rename_current, "F2")
        self.comment_action = action(_("Comment…"), self._comment_current)
        self.branch_action = action(_("Branch from here"), self._branch_current)
        self.delete_action = action(_("Delete step"), self._delete_current, "Del")
        self.remove_step_action = action(
            _("Delete step (keep following steps)"), self._remove_step_current, "Shift+Del"
        )
        self._actions = (
            (self.rename_action, _("Rename")),
            (self.comment_action, _("Comment…")),
            (self.branch_action, _("Branch from here")),
            (self.delete_action, _("Delete step")),
            (self.remove_step_action, _("Delete step (keep following steps)")),
        )

    def retranslate(self, _language: object = None) -> None:
        for act, text in self._actions:
            act.setText(str(text))

    def _on_context_menu(self, pos: QtCore.QPoint) -> None:
        nid = self.model.node_id(self.view.indexAt(pos))
        if nid is None:
            return
        self.app.state.current = nid
        menu = QtWidgets.QMenu(self)
        for act, _text in self._actions:
            menu.addAction(act)
        if self.extra_actions:
            menu.addSeparator()
            menu.addActions(self.extra_actions)
        menu.exec(self.view.viewport().mapToGlobal(pos))

    # --- operations (also used by tests / other UI) ------------------------------------
    def rename(self, nid: str, name: str) -> None:
        self.app.commands.rename(nid, name)

    def set_comment(self, nid: str, comment: str) -> None:
        self.app.commands.set_comment(nid, comment)

    def delete(self, nid: str) -> None:
        self.app.commands.remove_subtree(nid)

    def remove_step(self, nid: str) -> bool:
        """Delete one step, keep the steps after it; refusals become an error message."""
        from datacook.engine.restructure import StepError

        node = self.app.session.get(nid)
        children = [c.id for c in self.app.session.children(nid)]
        try:
            self.app.commands.remove_step(nid)
        except StepError as e:
            self.app.notify(str(e), "error", nid)
            return False
        if node is not None and self.app.state.current in (None, nid):
            self.app.state.current = children[0] if children else node.parents[0]
        return True

    def branch(self, nid: str) -> None:
        """Select `nid`: the next added step becomes its child (a branch if it has one)."""
        self.app.state.current = nid
        self.app.notify(
            str(_("Add a step to branch from {name}")).format(name=self.model.label(nid)),
            "info",
            nid,
        )

    def _rename_current(self) -> None:
        if (nid := self.app.state.current) is not None:
            self.view.edit(self.model.index_of(nid))

    def _comment_current(self) -> None:
        nid = self.app.state.current
        node = None if nid is None else self.app.session.get(nid)
        if nid is None or node is None:
            return
        text, ok = QtWidgets.QInputDialog.getMultiLineText(
            self, str(_("Comment")), self.model.label(nid), node.comment or ""
        )
        if ok:
            self.set_comment(nid, text)

    def _remove_step_current(self) -> None:
        if (nid := self.app.state.current) is not None:
            self.remove_step(nid)

    def _branch_current(self) -> None:
        if (nid := self.app.state.current) is not None:
            self.branch(nid)

    def _delete_current(self) -> None:
        if (nid := self.app.state.current) is not None:
            self.delete(nid)

    # --- selection sync ----------------------------------------------------------------
    def _on_row_changed(self, current: QtCore.QModelIndex, _previous: object) -> None:
        if self._syncing:
            return
        nid = self.model.node_id(current)
        if nid is not None:
            self.app.state.current = nid

    def _on_current_changed(self, _old: object, new: str | None) -> None:
        self._syncing = True
        try:
            index = self.model.index_of(new)
            selection = self.view.selectionModel()
            if index.isValid():
                self.view.scrollTo(index)
                selection.setCurrentIndex(
                    index,
                    QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
                    | QtCore.QItemSelectionModel.SelectionFlag.Rows,
                )
            else:
                selection.clear()
        finally:
            self._syncing = False

    def _on_rows_inserted(self, parent: QtCore.QModelIndex, _first: int, _last: int) -> None:
        if parent.isValid():
            self.view.expand(parent)
        current = self.app.state.current
        if current is not None and self.view.selectionModel().currentIndex() != (
            self.model.index_of(current)
        ):
            self._on_current_changed(None, current)


def create(app: AppController, _window: MainWindow) -> QtWidgets.QWidget:
    return NodeTreeWidget(app)


DOCKS = (DockSpec("nodetree", _("Steps"), "left", create),)


def install(app: AppController, window: MainWindow) -> None:
    widget = window.widgets.get("nodetree")
    if not isinstance(widget, NodeTreeWidget):
        return
    menu = window.menu("steps")
    for act, _text in widget._actions:
        menu.addAction(act)
