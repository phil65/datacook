"""MainWindow shell: dock areas, menus, status bar; filled by the UI modules.

Docks are built from `DockSpec`s of the modules in `uimodules.UI_MODULES`; the window owns
no data and no behaviour beyond layout, menus, the window title (project file name + dirty
marker) and the unsaved-changes check on close (delegated to `window.project`, the
`ProjectController`, when installed).
"""

import contextlib
from typing import TYPE_CHECKING, Protocol

from prettyqt.qt import QtCore, QtWidgets

from datacook.app import style, uimodules
from datacook.i18n import _


if TYPE_CHECKING:
    import pathlib
    from types import ModuleType

    from prettyqt.qt import QtGui

    from datacook.app.controllers import AppController
    from datacook.app.uimodules import DockSpec


_AREAS = {
    "left": QtCore.Qt.DockWidgetArea.LeftDockWidgetArea,
    "right": QtCore.Qt.DockWidgetArea.RightDockWidgetArea,
    "bottom": QtCore.Qt.DockWidgetArea.BottomDockWidgetArea,
}

MENUS = {
    "file": _("&File"),
    "edit": _("&Edit"),
    "view": _("&View"),
    "steps": _("&Steps"),
    "help": _("&Help"),
}
"""Menu keys for `MainWindow.menu()`, in menu bar order."""

DOCK_SIZES = {"left": 340, "right": 340, "bottom": 210}
"""Initial width (left / right) or height (bottom) of the dock areas in pixels."""


class CloseGuard(Protocol):
    """What the window asks before closing (the `ProjectController`)."""

    def close_requested(self) -> bool:
        """False: keep the window open (unsaved changes, user cancelled)."""
        ...


class MainWindow(QtWidgets.QMainWindow):
    def __init__(
        self,
        app: AppController,
        modules: tuple[str, ...] | None = None,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.app = app
        self.setObjectName("datacook-main")
        self.docks: dict[str, QtWidgets.QDockWidget] = {}
        """Dock id -> QDockWidget (its `widget()` is what the spec created)."""
        self.widgets: dict[str, QtWidgets.QWidget] = {}
        """Dock id -> created widget (also central / status widgets)."""
        self.specs: dict[str, DockSpec] = {}
        self._menus: dict[str, QtWidgets.QMenu] = {}
        self._closed = False
        self.project: CloseGuard | None = None
        """Set by `controllers.project.install()`: asked on close (unsaved changes)."""
        self.recipes: QtCore.QObject | None = None
        """Set by `docks.recipes`: the `RecipeController` (recipe library, apply)."""
        self.project_path: pathlib.Path | None = None
        """The project file shown in the title (None: not saved yet)."""
        for key in MENUS:
            self.menu(key)
        self._add_edit_actions()
        self.setDockNestingEnabled(True)
        self.statusBar()
        self.resize(1400, 900)
        names = uimodules.UI_MODULES if modules is None else modules
        self.modules: list[ModuleType] = uimodules.load_modules(names)
        for module in self.modules:
            for spec in getattr(module, "DOCKS", ()):
                self.add_dock(spec)
        if self.centralWidget() is None:
            placeholder = QtWidgets.QLabel(str(_("No data view installed")))
            placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.setCentralWidget(placeholder)
        for module in self.modules:
            install = getattr(module, "install", None)
            if install is not None:
                install(app, self)
        # The first dock of a tab group stays the visible tab (Code before Messages,
        # Parameters before Columns), whatever order the modules added them in.
        for spec in self.specs.values():
            if spec.tabify_with in self.docks:
                self.docks[spec.tabify_with].raise_()
        self._initial_dock_sizes()
        style.apply(self)
        app.commands.undo_stack.cleanChanged.connect(self._update_title)
        app.state.language_changed.connect(self.retranslate)
        self._update_title()

    # --- building ----------------------------------------------------------------------
    def add_dock(self, spec: DockSpec) -> QtWidgets.QWidget:
        if spec.id in self.specs:
            msg = f"dock {spec.id!r} registered twice"
            raise ValueError(msg)
        widget = spec.create(self.app, self)
        self.specs[spec.id] = spec
        self.widgets[spec.id] = widget
        if spec.area == "central":
            self.setCentralWidget(widget)
            return widget
        if spec.area == "status":
            self.statusBar().addPermanentWidget(widget)
            return widget
        dock = QtWidgets.QDockWidget(str(spec.title), self)
        dock.setObjectName(spec.id)
        dock.setWidget(widget)
        self.addDockWidget(_AREAS[spec.area], dock)
        if spec.tabify_with and spec.tabify_with in self.docks:
            self.tabifyDockWidget(self.docks[spec.tabify_with], dock)
        dock.setVisible(spec.visible)
        self.docks[spec.id] = dock
        self.menu("view").addAction(dock.toggleViewAction())
        return widget

    def _initial_dock_sizes(self) -> None:
        """Room for the step names in a deep tree, the params form and the code pane."""
        horizontal, vertical = QtCore.Qt.Orientation.Horizontal, QtCore.Qt.Orientation.Vertical
        for area, size, orientation in (
            ("left", DOCK_SIZES["left"], horizontal),
            ("right", DOCK_SIZES["right"], horizontal),
            ("bottom", DOCK_SIZES["bottom"], vertical),
        ):
            docks = [
                self.docks[spec.id]
                for spec in self.specs.values()
                if spec.area == area and spec.id in self.docks and not spec.tabify_with
            ]
            if docks:
                self.resizeDocks(docks, [size] * len(docks), orientation)

    def menu(self, key: str, title: object = None) -> QtWidgets.QMenu:
        """The menu `key` ("file", "edit", "view", "steps", "help" or a new one)."""
        if key not in self._menus:
            text = str(title if title is not None else MENUS.get(key, key))
            menu = self.menuBar().addMenu(text)
            menu.setObjectName(f"menu-{key}")
            self._menus[key] = menu
        return self._menus[key]

    def _add_edit_actions(self) -> None:
        stack = self.app.commands.undo_stack
        edit = self.menu("edit")
        self.undo_action: QtGui.QAction = stack.createUndoAction(self, str(_("Undo")))
        self.undo_action.setShortcut("Ctrl+Z")
        self.redo_action: QtGui.QAction = stack.createRedoAction(self, str(_("Redo")))
        self.redo_action.setShortcut("Ctrl+Shift+Z")
        edit.addAction(self.undo_action)
        edit.addAction(self.redo_action)

    # --- state -------------------------------------------------------------------------
    def retranslate(self, _language: object = None) -> None:
        for key, menu in self._menus.items():
            if key in MENUS:
                menu.setTitle(str(MENUS[key]))
        for dock_id, dock in self.docks.items():
            dock.setWindowTitle(str(self.specs[dock_id].title))
        self._update_title()

    def set_project_path(self, path: pathlib.Path | None) -> None:
        self.project_path = path
        self._update_title()

    def _update_title(self, clean: bool | None = None) -> None:
        # `clean` comes from `cleanChanged`, which QUndoStack also emits from its
        # destructor (clear()): do not touch the stack then.
        if clean is None:
            clean = self.app.commands.is_clean()
        name = self.project_path.name if self.project_path else str(_("Untitled"))
        self.setWindowTitle(f"{name}{'' if clean else '*'} - DataCook")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        if self._closed:
            super().closeEvent(event)
            return
        if self.project is not None and not self.project.close_requested():
            event.ignore()
            return
        self._closed = True
        with contextlib.suppress(RuntimeError):  # stack already deleted
            self.app.commands.undo_stack.cleanChanged.disconnect(self._update_title)
        self.app.close()
        super().closeEvent(event)
