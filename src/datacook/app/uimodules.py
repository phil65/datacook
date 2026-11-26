"""Registration point for docks, status bar widgets and actions (no shared file to edit).

`UI_MODULES` already lists every planned UI module. A module that does not exist yet is
skipped, so a work package only *creates* its module; nothing else needs an edit. A module
may define:

- `DOCKS: Sequence[DockSpec]`: widgets the main window puts into a dock area, the central
  area or the status bar (`create(app, window)` builds the widget);
- `install(app, window) -> None`: called after all docks exist (menus, toolbar actions,
  shortcuts, the op palette).
"""

from dataclasses import dataclass
import importlib
from typing import TYPE_CHECKING, Literal


if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

    from prettyqt.qt import QtWidgets

    from datacook.app.controllers import AppController
    from datacook.app.mainwindow import MainWindow


type Area = Literal["left", "right", "bottom", "central", "status"]


@dataclass(frozen=True, slots=True)
class DockSpec:
    id: str
    """Object name of the dock (window state, `window.docks[id]`)."""
    title: object
    """`LazyText` (`_("…")`) or str; converted with `str()` on every retranslate."""
    area: Area
    create: Callable[[AppController, MainWindow], QtWidgets.QWidget]
    tabify_with: str | None = None
    """Put this dock as a tab onto the dock with that id (same area)."""
    visible: bool = True


UI_MODULES: tuple[str, ...] = (
    "datacook.app.docks.dataview",  # WP B (central)
    "datacook.app.docks.nodetree",  # WP B (left)
    "datacook.app.docks.code",  # WP B (bottom)
    "datacook.app.widgets.memoryindicator",  # WP B (status)
    "datacook.app.docks.params",  # WP C (right)
    "datacook.app.actions",  # WP C (menus, toolbar, op palette: install())
    "datacook.app.controllers.project",  # WP C (install(): file menu, open / save)
    "datacook.app.docks.schema",  # WP D (right, tab with params)
    "datacook.app.docks.messages",  # WP D (bottom, tab with code)
    "datacook.app.docks.recipes",  # O1 (right, tab with params; Steps > Recipes)
)


def load_modules(names: tuple[str, ...] = UI_MODULES) -> list[ModuleType]:
    """Import the UI modules that exist (a missing module is skipped, a broken one raises)."""
    modules = []
    for name in names:
        try:
            modules.append(importlib.import_module(name))
        except ModuleNotFoundError as e:
            if e.name is None or not (name == e.name or name.startswith(f"{e.name}.")):
                raise
    return modules
