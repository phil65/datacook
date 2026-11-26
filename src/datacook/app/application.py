"""QApplication setup, settings, language switch and the `datacook` GUI entry point.

The app runs on a plain `QApplication`, not prettyqt's `widgets.Application`: prettyqt
widgets work without it (prettyqt >= 1.63.1), and its extras (coroutine slots via an
`AsyncRunner` that wraps `SignalInstance.connect` process-wide, theme / stylesheet helpers)
bring nothing here: background work goes through `JobRunner`'s executors, and a wrapped
`connect` on every signal connection is a global side effect we do not want. Checked
2026-11-25: all app tests pass under either class.
"""

import logging
import pathlib
import sys
from typing import TYPE_CHECKING

from prettyqt.custom_widgets.pydanticform import PydanticForm
from prettyqt.qt import QtCore, QtGui, QtWidgets

from datacook import allocator, i18n
from datacook.app.controllers import AppController
from datacook.app.mainwindow import MainWindow
from datacook.app.settings import AppSettings
from datacook.i18n import _


if TYPE_CHECKING:
    from collections.abc import Sequence


logger = logging.getLogger(__name__)


LANGUAGES: dict[str, str] = {"en": "English", "de": "Deutsch"}
"""Languages offered in View > Language (code -> name in that language)."""

_qt_translator: QtCore.QTranslator | None = None


def system_language() -> str | None:
    """The system UI language if we ship a catalog for it, else None (English)."""
    code = QtCore.QLocale.system().name().split("_")[0]
    return code if code in LANGUAGES else None


def _install_qt_translator(language: str | None) -> None:
    """Swap the QTranslator for Qt's own strings (qtbase_<lang>.qm of the Qt install)."""
    global _qt_translator
    qapp = QtCore.QCoreApplication.instance()
    if qapp is None:
        return
    if _qt_translator is not None:
        qapp.removeTranslator(_qt_translator)
        _qt_translator = None
    if language in (None, "en"):
        return
    translator = QtCore.QTranslator(qapp)
    path = QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(f"qtbase_{language}", path):
        qapp.installTranslator(translator)
        _qt_translator = translator
    else:
        logger.info("no Qt translation qtbase_%s in %s", language, path)


def set_language(app: AppController, language: str | None) -> None:
    """Switch the UI language at runtime (docks follow `AppState.language_changed`).

    `language`: a code (`LANGUAGES`) or None (source strings, English). Switches the
    gettext catalog (`datacook.i18n`) and Qt's translator, then `app.state.language`.
    """
    try:
        i18n.set_language(language)
    except OSError:
        logger.warning("no translation for %r", language)
        return
    _install_qt_translator(language)
    app.state.language = language


def choose_language(app: AppController, language: str | None) -> None:
    """User choice (View > Language): store it in the settings file, then switch.

    `None` = system default (stored as None, resolved with `system_language()`).
    """
    app.state.update_settings(language=language).save()
    set_language(app, language or system_language())


def retranslate_forms(window: QtWidgets.QWidget) -> None:
    """`retranslate()` every PydanticForm in the window (params forms, dialogs)."""
    for form in window.findChildren(PydanticForm):
        form.retranslate()


class LanguageMenu(QtWidgets.QMenu):
    """View > Language: system default + `LANGUAGES` (checkable, saved in the settings)."""

    def __init__(self, app: AppController, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("menu-language")
        group = QtGui.QActionGroup(self)
        self.choices: dict[str | None, QtGui.QAction] = {None: self.addAction("")}
        self.addSeparator()
        for code, name in LANGUAGES.items():
            self.choices[code] = self.addAction(name)
        current = app.state.settings.language
        for code, action in self.choices.items():
            action.setCheckable(True)
            action.setChecked(code == current)
            action.setData(code)
            group.addAction(action)
            action.triggered.connect(lambda _checked=False, c=code: choose_language(app, c))
        app.state.language_changed.connect(self.retranslate)
        self.retranslate()

    def retranslate(self, _language: object = None) -> None:
        self.setTitle(str(_("Language")))
        self.choices[None].setText(str(_("System default")))
        if (window := self.parentWidget()) is not None:
            retranslate_forms(window)


def add_language_menu(app: AppController, window: MainWindow) -> LanguageMenu:
    """Add View > Language (`LanguageMenu`) to the main window."""
    menu = LanguageMenu(app, window)
    window.menu("view").addMenu(menu)
    return menu


def create_window(settings: AppSettings | None = None) -> MainWindow:
    """AppController + MainWindow (needs a QApplication)."""
    settings = settings or AppSettings.load()
    app = AppController(settings=settings)
    if language := settings.language or system_language():
        set_language(app, language)
    return MainWindow(app)


def open_paths(window: MainWindow, paths: Sequence[str]) -> None:
    """Command line files: open a project, import a recipe, or read a data file (dialog)."""
    from datacook.app.controllers.project import PROJECT_SUFFIX, ProjectController
    from datacook.app.docks.recipes import RecipeController
    from datacook.engine.recipes import SUFFIX as RECIPE_SUFFIX

    project = window.project
    if not isinstance(project, ProjectController):
        return
    for path in paths:
        suffix = pathlib.Path(path).suffix.lower()
        if suffix == PROJECT_SUFFIX:
            project.open(path)
        elif suffix == RECIPE_SUFFIX:
            if isinstance(window.recipes, RecipeController):
                window.recipes.import_file(path)
        else:
            project.open_data(path)


ICON_DIR = pathlib.Path(__file__).parent.parent / "resources" / "icons"
"""App icon in 16-256 px (`resources/icon.svg` is the master, `icon.ico` for Windows)."""


def app_icon() -> QtGui.QIcon:
    """The DataCook icon with every size from `ICON_DIR`."""
    icon = QtGui.QIcon()
    for path in sorted(ICON_DIR.glob("*.png")):
        icon.addFile(str(path))
    return icon


def main(argv: Sequence[str] | None = None) -> int:
    """`datacook [PROJECT.datacook | DATA_FILE ...]`."""
    logging.basicConfig(level=logging.INFO)
    allocator.configure()  # no-op after `datacook.app.main`; else glibc + Python-side pool
    args = list(sys.argv if argv is None else argv)
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication(args)
    qapp.setApplicationName("DataCook")
    QtGui.QGuiApplication.setWindowIcon(app_icon())
    window = create_window()
    window.app.state.settings_changed.connect(lambda settings: settings.save())  # recent files
    window.show()
    # Qt removes the options it handles (-style, ...) from the QApplication's arguments
    paths = [a for a in QtCore.QCoreApplication.arguments()[1:] if not a.startswith("-")]
    QtCore.QTimer.singleShot(0, lambda: open_paths(window, paths))
    return qapp.exec()
