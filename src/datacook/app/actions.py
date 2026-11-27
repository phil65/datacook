"""Op actions: one `QAction` per registered op, the Steps menu and the op palette.

`OpActions` builds the actions from the op registry (title, category, icon, description);
triggering one opens a params preview (`app.preview.start_add`) for a new step on the
current node. Readers (`n_inputs == 0`) start a root; merge-like ops (`n_inputs == 2`) ask
for the second input, ops taking two or more (`variadic`, concat) for the other inputs.
The Steps menu groups the actions by category; the palette (`CommandPalette`,
Ctrl+Shift+P) lists all of them. Both follow language changes.
"""

import logging
from typing import TYPE_CHECKING

from prettyqt import custom_widgets, iconprovider
from prettyqt.qt import QtCore, QtGui, QtWidgets

from datacook.engine import categories
from datacook.i18n import _


if TYPE_CHECKING:
    from collections.abc import Callable

    from datacook.app.controllers import AppController
    from datacook.app.mainwindow import MainWindow
    from datacook.engine import Node, Op


logger = logging.getLogger(__name__)

PALETTE_SHORTCUT = "Ctrl+Shift+P"
CATEGORY_ORDER = (
    categories.SOURCE,
    categories.GENERAL,
    categories.COLUMNS,
    categories.ROWS,
    categories.FILTER,
    categories.NAN,
    categories.CATEGORICAL,
    categories.CONVERSION,
    categories.TEXT,
    categories.DATETIME,
    categories.TIMESERIES,
    categories.RESHAPE,
    categories.COMBINE,
    categories.STATS,
    categories.ML,
    categories.CODE,
)
"""Order of the category submenus of the Steps menu."""


def node_label(app: AppController, node: Node) -> str:
    """`name` or op title of a node (for choosers and messages)."""
    if node.name:
        return node.name
    op = app.session.registry.get(node.op_id) if node.op_id in app.session.registry else None
    return str(op.title) if op is not None else node.op_id


class OpActions(QtCore.QObject):
    """The op actions, the Steps menu content and the palette of one main window."""

    def __init__(self, app: AppController, window: QtWidgets.QWidget):
        super().__init__(window)
        self.setObjectName("op-actions")
        self.app = app
        self.actions: dict[str, QtGui.QAction] = {}
        """Op id -> action (registry order)."""
        self.category_menus: dict[str, QtWidgets.QMenu] = {}
        self.choose_input: Callable[[str, list[Node]], str | None] = self._ask_input
        """`(op_id, candidates) -> node id or None`: the second input of a 2-input op."""
        self.choose_inputs: Callable[[str, list[Node]], list[str] | None] = self._ask_inputs
        """`(op_id, candidates) -> node ids or None`: the other inputs of a variadic op."""
        for op in app.session.registry:
            self.actions[op.id] = self._make_action(op)
        self.palette = custom_widgets.CommandPalette()
        self.palette.setObjectName("op-palette")
        self.palette.setParent(window, QtCore.Qt.WindowType.SubWindow)
        self.palette.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.palette.setMinimumWidth(420)
        if (pal_layout := self.palette.layout()) is not None:
            pal_layout.setContentsMargins(10, 10, 10, 10)
            pal_layout.setSpacing(8)
        table = self.palette._table
        table.horizontalHeader().hide()
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(24)
        table.setAlternatingRowColors(True)
        for col in range(2, table.model().columnCount()):
            table.setColumnHidden(col, True)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(0, 220)
        table.pressed.connect(lambda _idx: self.palette.hide())
        self.palette.hide()
        self.palette.set_actions(self.actions.values())
        self.palette_action = QtGui.QAction(window)
        self.palette_action.setObjectName("action-palette")
        self.palette_action.setShortcut(PALETTE_SHORTCUT)
        self.palette_action.setShortcutContext(QtCore.Qt.ShortcutContext.WindowShortcut)
        self.palette_action.triggered.connect(self.show_palette)
        window.addAction(self.palette_action)
        self.edit_action = QtGui.QAction(window)
        self.edit_action.setObjectName("action-edit-step")
        self.edit_action.setShortcut("Ctrl+E")  # F2 = rename in the tree
        self.edit_action.triggered.connect(self.edit_current)
        self.cancel_action = QtGui.QAction(window)
        self.cancel_action.setObjectName("action-cancel-preview")
        self.cancel_action.setShortcut("Esc")  # enabled only while a preview is open
        self.cancel_action.triggered.connect(app.preview.cancel)
        app.state.language_changed.connect(self.retranslate)
        app.state.current_changed.connect(self._update_enabled)
        app.state.preview_changed.connect(self._update_enabled)
        self.retranslate()

    def parent_widget(self) -> QtWidgets.QWidget | None:
        """The main window (not stored: no Python reference cycle with it)."""
        parent = self.parent()
        return parent if isinstance(parent, QtWidgets.QWidget) else None

    # --- building ----------------------------------------------------------------------
    def _make_action(self, op: type[Op]) -> QtGui.QAction:
        action = QtGui.QAction(self)
        action.setObjectName(f"op-{op.id}")
        action.setData(op.id)
        try:
            action.setIcon(iconprovider.get_icon(op.icon))
        except Exception:  # noqa: BLE001 - an unknown icon name must not break the menu
            logger.debug("no icon %r for op %s", op.icon, op.id)
        action.setEnabled(op.available())
        action.triggered.connect(lambda _checked=False, op_id=op.id: self.start(op_id))
        return action

    def ops_by_category(self) -> list[type[Op]]:
        """Registry ops, grouped in the order of `engine.categories` (others last)."""
        order = {c.id: i for i, c in enumerate(CATEGORY_ORDER)}
        ops = list(self.app.session.registry)
        return sorted(ops, key=lambda op: order.get(op.category.id, len(order)))

    def fill_menu(self, menu: QtWidgets.QMenu) -> None:
        """Steps menu: Palette, Edit step, Cancel, then one submenu per category."""
        menu.addAction(self.palette_action)
        menu.addAction(self.edit_action)
        menu.addAction(self.cancel_action)
        menu.addSeparator()
        for op in self.ops_by_category():
            category = op.category
            sub = self.category_menus.get(category.id)
            if sub is None:
                sub = menu.addMenu(str(category.title))
                sub.setObjectName(f"menu-category-{category.id}")
                try:
                    sub.setIcon(iconprovider.get_icon(category.icon))
                except Exception:  # noqa: BLE001
                    logger.debug("no icon %r for category %s", category.icon, category.id)
                self.category_menus[category.id] = sub
            sub.addAction(self.actions[op.id])

    def retranslate(self, _language: object = None) -> None:
        registry = self.app.session.registry
        for op_id, action in self.actions.items():
            op = registry.get(op_id)
            action.setText(str(op.title))
            tip = f"{op.category.title}: {op.description}" if str(op.description) else ""
            if not op.available():
                needs = str(_("needs the extra {extra!r}")).format(extra=op.extra or "?")
                tip = f"{tip} ({needs})" if tip else needs
            action.setToolTip(tip or str(op.category.title))
            action.setStatusTip(str(op.description))
        for op in registry:
            if (sub := self.category_menus.get(op.category.id)) is not None:
                sub.setTitle(str(op.category.title))
        self.palette_action.setText(str(_("Command palette…")))
        self.edit_action.setText(str(_("Edit step…")))
        self.cancel_action.setText(str(_("Cancel preview")))
        self.palette._line.setPlaceholderText(str(_("Search operations…")))
        self.palette.set_actions(self.actions.values())
        self._update_enabled()

    def _update_enabled(self, *_args: object) -> None:
        current = self.app.state.current
        editable = current is not None and current in self.app.session
        self.edit_action.setEnabled(editable)
        self.cancel_action.setEnabled(self.app.state.preview is not None)

    # --- behaviour ---------------------------------------------------------------------
    def show_palette(self) -> None:
        self.palette._line.setText("")
        parent = self.parent_widget()
        if parent is not None:
            width = min(680, max(420, parent.width() - 80))
            height = min(380, max(240, parent.height() - 120))
            x = max(12, (parent.width() - width) // 2)
            y = max(36, int(parent.height() * 0.12))
            self.palette.setGeometry(x, y, width, height)
        else:
            self.palette.resize(640, 340)
        QtWidgets.QWidget.show(self.palette)
        self.palette.raise_()
        self.palette._line.setFocus()

    def start(self, op_id: str) -> bool:  # noqa: PLR0911
        """Open a params preview for a new `op_id` step; False if it cannot start."""
        app = self.app
        op = app.session.registry.get(op_id)
        if not op.available():
            app.notify(
                str(_("{title} needs the extra {extra!r}")).format(title=op.title, extra=op.extra),
                "warning",
            )
            return False
        if op.n_inputs == 0:
            app.preview.start_add(op_id, ())
            return True
        current = app.state.current
        if current is None or current not in app.session:
            app.notify(_("Select a step first: the new step is added after it."), "warning")
            return False
        inputs = [current]
        if op.n_inputs == 2:  # noqa: PLR2004
            candidates = [n for n in app.session.nodes() if n.id != current]
            if not candidates:
                app.notify(
                    str(_("{title} needs a second table.")).format(title=op.title), "warning"
                )
                return False
            if op.variadic:
                others = self.choose_inputs(op_id, candidates)
                if not others:
                    return False
                inputs.extend(others)
            else:
                other = self.choose_input(op_id, candidates)
                if other is None:
                    return False
                inputs.append(other)
        elif op.n_inputs > 2:  # noqa: PLR2004
            app.notify(_("Ops with more than two inputs are not supported yet."), "warning")
            return False
        app.preview.start_add(op_id, inputs)
        return True

    def edit_current(self) -> bool:
        current = self.app.state.current
        if current is None or current not in self.app.session:
            return False
        self.app.preview.start_edit(current)
        return True

    def _ask_input(self, op_id: str, candidates: list[Node]) -> str | None:
        op = self.app.session.registry.get(op_id)
        labels = [f"{node_label(self.app, n)} [{n.id[:6]}]" for n in candidates]
        label, ok = QtWidgets.QInputDialog.getItem(
            self.parent_widget(),
            str(op.title),
            str(_("Second table (right side):")),
            labels,
            0,
            False,
        )
        if not ok:
            return None
        return candidates[labels.index(label)].id

    def _ask_inputs(self, op_id: str, candidates: list[Node]) -> list[str] | None:
        """A list of the candidates to check; the checked ones in list order."""
        op = self.app.session.registry.get(op_id)
        dialog = QtWidgets.QDialog(self.parent_widget())
        dialog.setWindowTitle(str(op.title))
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.addWidget(QtWidgets.QLabel(str(_("Tables to add after the current one:"))))
        items = QtWidgets.QListWidget(dialog)
        for node in candidates:
            item = QtWidgets.QListWidgetItem(f"{node_label(self.app, node)} [{node.id[:6]}]")
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Unchecked)
            items.addItem(item)
        layout.addWidget(items)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        checked = QtCore.Qt.CheckState.Checked
        return [n.id for i, n in enumerate(candidates) if items.item(i).checkState() == checked]


def install(app: AppController, window: MainWindow) -> None:
    actions = OpActions(app, window)
    actions.fill_menu(window.menu("steps"))
