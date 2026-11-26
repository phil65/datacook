"""ProjectController: project files, opening data files, exports (File menu).

- **Project**: New / Open / Save / Save As of the engine's JSON project format
  (`engine.project`). Opening = `app.new_project()` + adding the file's nodes directly to the
  session (not undoable: the undo history starts empty); the clean state of the undo stack is
  the saved state (`dirty`). Recent files live in `AppSettings.recent_files`.
- **Open data**: file chooser with the reader formats of the format registry -> the reader
  op's Params form with a preview of the first rows (`ReaderDialog`, "reader-preview" job
  slot) -> an undoable `add_node` of the reader record (a new root), which becomes current.
- **Export**: the current node's frame through the CSV / Parquet / Excel writers (on the
  view pool, so a large write does not block the GUI), or the generated script of the
  current node (`session.render_code`).

- **Close**: `close_requested()` (asked by the main window) offers Save / Discard / Cancel
  when the project has unsaved changes.

Every dialog is a replaceable hook (`ask_open_path`, `ask_save_path`, `confirm_discard`,
`ask_save_changes`, `exec_dialog`, `ask_writer_params`), so tests drive the controller
without modal dialogs.
"""

import json
import pathlib
from typing import TYPE_CHECKING, Any, Literal, cast

from prettyqt import custom_widgets
from prettyqt.qt import QtCore, QtGui, QtWidgets

from datacook import i18n
from datacook.app.widgets.readerdialog import ReaderDialog
from datacook.engine import project
from datacook.engine.formats import FormatRegistry
from datacook.i18n import _


if TYPE_CHECKING:
    from collections.abc import Callable
    import concurrent.futures

    from datacook.app.controllers import AppController
    from datacook.app.mainwindow import MainWindow
    from datacook.engine import Params
    from datacook.engine.formats import Writer
    from datacook.engine.session import Session


PROJECT_SUFFIX = ".datacook"
MAX_RECENT = 10
EXPORT_WRITERS = ("csv", "parquet", "excel")
EXPORT_SLOT = "export"

type SaveChoice = Literal["save", "discard", "cancel"]


def _filter(title: object, extensions: tuple[str, ...]) -> str:
    patterns = " ".join(f"*{ext}" for ext in extensions)
    return f"{title} ({patterns})"


class ProjectController(QtCore.QObject):
    path_changed = QtCore.Signal(object)
    """(pathlib.Path | None) the project file (None: not saved yet)."""
    exported = QtCore.Signal(object)
    """(pathlib.Path) an export finished."""

    def __init__(self, app: AppController, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("project-controller")
        self.app = app
        self.formats = FormatRegistry(app.session.registry)
        self.path: pathlib.Path | None = None
        # dialog hooks (replace in tests)
        self.confirm_discard: Callable[[], bool] = self._confirm_discard
        self.ask_save_changes: Callable[[], SaveChoice] = self._ask_save_changes
        self.ask_open_path: Callable[[str, str], str | None] = self._ask_open_path
        self.ask_save_path: Callable[[str, str], str | None] = self._ask_save_path
        self.exec_dialog: Callable[[QtWidgets.QDialog], bool] = self._exec_dialog
        self.ask_writer_params: Callable[[type[Writer]], Params | None] = self._ask_writer_params

    def parent_widget(self) -> QtWidgets.QWidget | None:
        """The main window (not stored: no Python reference cycle with it)."""
        parent = self.parent()
        return parent if isinstance(parent, QtWidgets.QWidget) else None

    # --- state -------------------------------------------------------------------------
    @property
    def dirty(self) -> bool:
        """Unsaved changes (the undo stack is not at its clean state)."""
        return not self.app.commands.is_clean()

    def _set_path(self, path: pathlib.Path | None) -> None:
        self.path = path
        self.path_changed.emit(path)

    def recent_files(self) -> tuple[str, ...]:
        return self.app.state.settings.recent_files

    def _add_recent(self, path: pathlib.Path) -> None:
        entry = str(path)
        recent = (entry, *(p for p in self.recent_files() if p != entry))[:MAX_RECENT]
        self.app.state.update_settings(recent_files=recent)

    def _fail(self, text: object, path: object, error: BaseException) -> None:
        self.app.notify(str(text).format(path=path, error=error), "error")

    # --- project -----------------------------------------------------------------------
    def close_requested(self) -> bool:
        """Window close: True if it may close (saved, discarded or nothing to save)."""
        if not self.dirty:
            return True
        match self.ask_save_changes():
            case "save":
                return self.save()
            case "discard":
                return True
            case _:
                return False

    def new(self) -> bool:
        if self.dirty and not self.confirm_discard():
            return False
        self.app.new_project()
        self._set_path(None)
        return True

    def open(self, path: str | pathlib.Path | None = None) -> bool:
        """Open a project file (asks for one if `path` is None)."""
        if path is None:
            filters = _filter(_("DataCook project"), (PROJECT_SUFFIX,))
            chosen = self.ask_open_path(str(_("Open project")), filters)
            if not chosen:
                return False
            path = chosen
        if self.dirty and not self.confirm_discard():
            return False
        path = pathlib.Path(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            self.app.notify(
                str(_("Cannot open {path}: {error}")).format(path=path, error=e), "error"
            )
            return False
        self.app.new_project()
        try:
            # project files carry their node ids; opening is not an undoable step
            project.from_dict(cast("Session", self.app.session), data)
        except (project.ProjectError, KeyError, TypeError, ValueError) as e:
            self.app.new_project()
            self.app.notify(
                str(_("Cannot open {path}: {error}")).format(path=path, error=e), "error"
            )
            return False
        self.app.commands.clear()
        self.app.commands.set_clean()
        nodes = self.app.session.nodes()
        if nodes:
            self.app.state.current = nodes[-1].id
        self._set_path(path)
        self._add_recent(path)
        self.app.notify(str(_("Opened {path}")).format(path=path.name))
        return True

    def save(self) -> bool:
        if self.path is None:
            return self.save_as()
        return self._write_project(self.path)

    def save_as(self, path: str | pathlib.Path | None = None) -> bool:
        if path is None:
            filters = _filter(_("DataCook project"), (PROJECT_SUFFIX,))
            chosen = self.ask_save_path(str(_("Save project")), filters)
            if not chosen:
                return False
            path = pathlib.Path(chosen)
            if not path.suffix:
                path = path.with_suffix(PROJECT_SUFFIX)
        return self._write_project(pathlib.Path(path))

    def _write_project(self, path: pathlib.Path) -> bool:
        try:
            project.save(cast("Session", self.app.session), path)
        except OSError as e:
            self.app.notify(
                str(_("Cannot save {path}: {error}")).format(path=path, error=e), "error"
            )
            return False
        self.app.commands.set_clean()
        self._set_path(path)
        self._add_recent(path)
        self.app.notify(str(_("Saved {path}")).format(path=path.name))
        return True

    # --- data files --------------------------------------------------------------------
    def reader_filters(self) -> str:
        parts = []
        all_exts: list[str] = []
        for fmt in self.formats.formats():
            if fmt.reader is None or not getattr(fmt.reader, "extensions", ()):
                continue
            exts = tuple(fmt.reader.extensions)  # ty: ignore[missing-attribute]
            all_exts.extend(exts)
            title = fmt.title if fmt.available() else f"{fmt.title} ({_('needs')} {fmt.extra})"
            parts.append(_filter(title, exts))
        return ";;".join([_filter(_("All data files"), tuple(all_exts)), *parts])

    def open_data(self, path: str | pathlib.Path | None = None) -> str | None:
        """Reader dialog for a data file; returns the new root node id (or None)."""
        if path is None:
            path = self.ask_open_path(str(_("Open data file")), self.reader_filters())
            if not path:
                return None
        try:
            op = self.formats.reader_for(path)
        except KeyError:
            suffix = pathlib.Path(path).suffix or str(path)
            self.app.notify(str(_("No reader for {suffix} files")).format(suffix=suffix), "error")
            return None
        if not op.available():
            msg = str(_("{title} needs the extra {extra!r}")).format(title=op.title, extra=op.extra)
            self.app.notify(msg, "error")
            return None
        dialog = ReaderDialog(self.app, op, str(path), self.parent_widget())
        try:
            if not self.exec_dialog(dialog):
                return None
            record = dialog.record()
        finally:
            dialog.stop()
            dialog.deleteLater()
        if record is None:
            return None
        node_id = self.app.commands.add_node(record)
        self.app.state.current = node_id
        return node_id

    # --- export ------------------------------------------------------------------------
    def export_data(
        self,
        writer_id: str,
        path: str | pathlib.Path | None = None,
        params: Params | None = None,
    ) -> bool:
        """Write the current node's frame (CSV / Parquet / Excel) on the view pool."""
        node_id = self.app.state.current
        if node_id is None:
            self.app.notify(_("Select a step to export."), "warning")
            return False
        writer = self.formats.writers.get(writer_id)
        if not writer.available():
            msg = str(_("{title} needs the extra {extra!r}")).format(
                title=writer.title, extra=writer.extra
            )
            self.app.notify(msg, "error")
            return False
        if path is None:
            title = str(_("Export {title}")).format(title=writer.title)
            chosen = self.ask_save_path(title, _filter(writer.title, writer.extensions))
            if not chosen:
                return False
            path = pathlib.Path(chosen)
            if not path.suffix:
                path = path.with_suffix(writer.extensions[0])
        if params is None:
            params = self.ask_writer_params(writer)
            if params is None:
                return False
        target = pathlib.Path(path)
        session = cast("Session", self.app.session)

        def done(future: concurrent.futures.Future[Any]) -> None:
            try:
                future.result()
            except Exception as e:  # noqa: BLE001 - reported to the user
                msg = str(_("Export to {path} failed: {error}")).format(path=target, error=e)
                self.app.notify(msg, "error", node_id)
                return
            self.app.notify(str(_("Exported {path}")).format(path=target.name), node_id=node_id)
            self.exported.emit(target)

        self.app.jobs.submit_view(
            EXPORT_SLOT, writer.write, session, node_id, target, params, on_done=done
        )
        return True

    def export_script(
        self, path: str | pathlib.Path | None = None, *, whole_tree: bool = False
    ) -> bool:
        """Write the generated Python script of the current node (or of the whole tree)."""
        node_id = self.app.state.current
        if node_id is None and not whole_tree:
            self.app.notify(_("Select a step to export."), "warning")
            return False
        if path is None:
            chosen = self.ask_save_path(
                str(_("Export script")), _filter(_("Python script"), (".py",))
            )
            if not chosen:
                return False
            path = pathlib.Path(chosen)
            if not path.suffix:
                path = path.with_suffix(".py")
        target = pathlib.Path(path)
        script = self.app.session.render_code(None if whole_tree else [node_id])  # ty: ignore[invalid-argument-type]
        try:
            target.write_text(script.text, encoding="utf-8")
        except OSError as e:
            msg = str(_("Export to {path} failed: {error}")).format(path=target, error=e)
            self.app.notify(msg, "error")
            return False
        self.app.notify(str(_("Exported {path}")).format(path=target.name), node_id=node_id)
        self.exported.emit(target)
        return True

    # --- default dialogs ---------------------------------------------------------------
    def _confirm_discard(self) -> bool:
        answer = QtWidgets.QMessageBox.question(
            self.parent_widget(),
            "DataCook",
            str(_("Discard the unsaved changes of this project?")),
            QtWidgets.QMessageBox.StandardButton.Discard
            | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Cancel,
        )
        return answer == QtWidgets.QMessageBox.StandardButton.Discard

    def _ask_save_changes(self) -> SaveChoice:
        buttons = QtWidgets.QMessageBox.StandardButton
        answer = QtWidgets.QMessageBox.question(
            self.parent_widget(),
            "DataCook",
            str(_("Save the changes of this project before closing?")),
            buttons.Save | buttons.Discard | buttons.Cancel,
            buttons.Save,
        )
        if answer == buttons.Save:
            return "save"
        return "discard" if answer == buttons.Discard else "cancel"

    def _start_dir(self) -> str:
        recent = self.recent_files()
        return str(pathlib.Path(recent[0]).parent) if recent else ""

    def _ask_open_path(self, title: str, filters: str) -> str | None:
        path, _filter_used = QtWidgets.QFileDialog.getOpenFileName(
            self.parent_widget(), title, self._start_dir(), filters
        )
        return path or None

    def _ask_save_path(self, title: str, filters: str) -> str | None:
        path, _filter_used = QtWidgets.QFileDialog.getSaveFileName(
            self.parent_widget(), title, self._start_dir(), filters
        )
        return path or None

    @staticmethod
    def _exec_dialog(dialog: QtWidgets.QDialog) -> bool:
        return dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted

    def _ask_writer_params(self, writer: type[Writer]) -> Params | None:
        if not writer.Params.model_fields:
            return writer.Params()
        dialog = custom_widgets.PydanticDialog(
            writer.Params,
            title=str(_("Export {title}")).format(title=writer.title),
            translate=i18n.translate,
            parent=self.parent_widget(),
        )
        try:
            params = dialog.get_value() if self.exec_dialog(dialog) else None
        finally:
            dialog.deleteLater()
        return cast("Params | None", params)


# --- menu --------------------------------------------------------------------------------


class ProjectMenu(QtCore.QObject):
    """File menu entries of a `ProjectController` (retranslated on language change)."""

    def __init__(self, controller: ProjectController, window: MainWindow):
        super().__init__(controller)
        self.controller = controller
        app = controller.app
        menu = window.menu("file")
        self._texts: dict[QtGui.QAction, object] = {}

        def action(text: object, slot: Callable[[], object], shortcut: str | None = None):
            act = QtGui.QAction(str(text), window)
            if shortcut:
                act.setShortcut(shortcut)
            act.triggered.connect(lambda _checked=False: slot())
            self._texts[act] = text
            return act

        self.new_action = action(_("&New project"), controller.new, "Ctrl+N")
        self.open_action = action(_("&Open project…"), controller.open, "Ctrl+O")
        self.recent_menu = QtWidgets.QMenu(str(_("Open &recent")), window)
        self.save_action = action(_("&Save project"), controller.save, "Ctrl+S")
        self.save_as_action = action(_("Save project &as…"), controller.save_as, "Ctrl+Shift+S")
        self.open_data_action = action(_("Open &data file…"), controller.open_data, "Ctrl+Shift+O")
        self.export_menu = QtWidgets.QMenu(str(_("&Export")), window)
        writers = controller.formats.writers
        for writer_id in EXPORT_WRITERS:
            if writer_id not in writers:
                continue
            writer = writers.get(writer_id)
            act = action(writer.title, lambda w=writer_id: controller.export_data(w))
            act.setObjectName(f"action-export-{writer_id}")
            self.export_menu.addAction(act)
        self.export_menu.addSeparator()
        self.script_action = action(_("Python script…"), controller.export_script)
        self.export_menu.addAction(self.script_action)
        menu.addAction(self.new_action)
        menu.addAction(self.open_action)
        menu.addMenu(self.recent_menu)
        menu.addAction(self.save_action)
        menu.addAction(self.save_as_action)
        menu.addSeparator()
        menu.addAction(self.open_data_action)
        menu.addMenu(self.export_menu)
        menu.addSeparator()
        self._update_recent()
        app.state.settings_changed.connect(self._update_recent)
        app.state.language_changed.connect(self.retranslate)

    def retranslate(self, _language: object = None) -> None:
        for act, text in self._texts.items():
            act.setText(str(text))
        self.recent_menu.setTitle(str(_("Open &recent")))
        self.export_menu.setTitle(str(_("&Export")))
        self._update_recent()

    def _update_recent(self, _settings: object = None) -> None:
        self.recent_menu.clear()
        recent = self.controller.recent_files()
        for entry in recent:
            act = self.recent_menu.addAction(entry)
            act.triggered.connect(lambda _checked=False, p=entry: self.controller.open(p))
        self.recent_menu.setEnabled(bool(recent))


def install(app: AppController, window: MainWindow) -> None:
    controller = ProjectController(app, window)
    ProjectMenu(controller, window)
    window.project = controller
    controller.path_changed.connect(window.set_project_path)
