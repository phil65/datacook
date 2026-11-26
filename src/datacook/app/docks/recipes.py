"""Recipes dock: the recipe library, creating recipes from steps, applying them.

- **Create** from the current step: "Save steps up to here as recipe" (the whole path; it
  starts with a reader, so it is an import recipe) or "Save step and following steps as
  recipe" (the step's subtree; its input is the step's parent). Recipes are stored in the
  library folder (`AppSettings.recipe_folder`, default `<user data dir>/recipes`).
- **Apply** to the current step or to several steps (each gets the recipe's steps as a new
  branch). The required columns are checked first (steps that were never computed are
  computed on the view pool for that); all nodes go through `app.commands` in one macro,
  so one undo removes everything a click added.
- **Import recipe**: run it as saved, or once per chosen file (the reader's path swapped).
- **Library**: rename, edit the description, delete, merge (a new recipe: the selected ones
  one after the other), import / export `.datacookrecipe` files.

Dialogs are replaceable hooks on `RecipeController` (`ask_text`, `ask_paths`,
`ask_save_path`, `ask_targets`, `confirm`), so tests run without modal dialogs.
"""

import html
import pathlib
from typing import TYPE_CHECKING, Any

from prettyqt.qt import QtCore, QtGui, QtWidgets

from datacook.app.uimodules import DockSpec
from datacook.engine import recipes
from datacook.engine.recipes import RecipeError, RecipeLibrary
from datacook.i18n import _


if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    import concurrent.futures

    from datacook.app.controllers import AppController
    from datacook.app.mainwindow import MainWindow
    from datacook.engine.recipes import Recipe


CHECK_SLOT = "recipe-check"
PATH_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1


def default_folder() -> pathlib.Path:
    from datacook.core.application import DATA_DIR

    return DATA_DIR / "recipes"


def _filter() -> str:
    title = str(_("DataCook recipe"))
    return f"{title} (*{recipes.SUFFIX})"


class RecipeController(QtCore.QObject):
    library_changed = QtCore.Signal()
    applied = QtCore.Signal(object)
    """(list[str]) ids of the nodes an apply / import added."""

    def __init__(self, app: AppController, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self.setObjectName("recipe-controller")
        self.app = app
        folder = app.state.settings.recipe_folder
        self.library = RecipeLibrary(
            pathlib.Path(folder) if folder else default_folder(), app.session.registry
        )
        # dialog hooks (replace in tests)
        self.ask_text: Callable[[str, str, str], str | None] = self._ask_text
        self.ask_paths: Callable[[str, str], list[str]] = self._ask_paths
        self.ask_save_path: Callable[[str, str], str | None] = self._ask_save_path
        self.ask_targets: Callable[[Recipe], list[str] | None] = self._ask_targets
        self.confirm: Callable[[str], bool] = self._confirm

    def parent_widget(self) -> QtWidgets.QWidget | None:
        parent = self.parent()
        return parent if isinstance(parent, QtWidgets.QWidget) else None

    def _error(self, error: object, node_id: str | None = None) -> None:
        self.app.notify(str(error), "error", node_id)

    def _label(self, nid: str) -> str:
        from datacook.app.docks.nodetree import node_label

        return node_label(self.app.session, nid)

    # --- creating ----------------------------------------------------------------------
    def create(
        self,
        node_id: str | None = None,
        *,
        subtree: bool = False,
        name: str | None = None,
        description: str = "",
    ) -> pathlib.Path | None:
        """Save the path to the step (or the step + following steps) as a library recipe."""
        nid = node_id or self.app.state.current
        if nid is None or nid not in self.app.session:
            return None
        if name is None:
            name = self.ask_text(str(_("Save as recipe")), str(_("Name")), self._label(nid))
            if not name:
                return None
        try:
            if subtree:
                recipe = recipes.from_subtree(
                    self.app.session, nid, name=name, description=description
                )
            else:
                recipe = recipes.from_path(
                    self.app.session, nid, name=name, description=description
                )
            path = self.library.save(recipe)
        except (RecipeError, OSError) as e:
            self._error(e, nid)
            return None
        self.library_changed.emit()
        msg = _("Recipe {name!r} saved ({n} steps)")
        self.app.notify(str(msg).format(name=recipe.name, n=len(recipe.steps)), "info", nid)
        return path

    # --- applying ----------------------------------------------------------------------
    def apply(self, recipe: Recipe, targets: Sequence[str] | None = None) -> list[str] | None:
        """Apply to the targets (default: the current step); None if it failed or waits.

        Targets whose columns are unknown (never computed) are computed first on the view
        pool; the recipe is then applied when they are done (`applied` signal).
        """
        if recipe.is_import:
            return self.run_import(recipe)
        if targets is None:
            current = self.app.state.current
            if current is None:
                self._error(_("Select a step to apply the recipe to."))
                return None
            targets = [current]
        targets = [t for t in targets if t in self.app.session]
        if not targets:
            return None
        unknown = [t for t in targets if self.app.session.summary(t) is None]
        if recipe.required_columns and unknown:
            session = self.app.session

            def compute() -> None:
                for t in unknown:
                    session.materialize(t)

            def done(future: concurrent.futures.Future[Any]) -> None:
                try:
                    future.result()
                except Exception as e:  # noqa: BLE001 - shown as a message
                    msg = _("Could not check the columns: {error}")
                    self._error(str(msg).format(error=e))
                    return
                self._apply_checked(recipe, targets)

            self.app.jobs.submit_view(CHECK_SLOT, compute, on_done=done)
            msg = _("Computing the steps to check the recipe's columns…")
            self.app.notify(msg)
            return None
        return self._apply_checked(recipe, targets)

    def _apply_checked(self, recipe: Recipe, targets: Sequence[str]) -> list[str] | None:
        targets = [t for t in targets if t in self.app.session]
        try:
            for t in targets:
                summary = self.app.session.summary(t)
                if summary is not None:
                    columns = [c.name for c in summary.columns]
                    recipes.check_target(recipe, columns, repr(self._label(t)))
            plans = [recipes.plan(recipe, t, registry=self.app.session.registry) for t in targets]
        except RecipeError as e:
            self._error(e, targets[0] if len(targets) == 1 else None)
            return None
        return self._add(recipe, plans)

    def _add(self, recipe: Recipe, plans: Sequence[Sequence[recipes.PlannedNode]]) -> list[str]:
        ids: list[str] = []
        text = str(_("Apply recipe {name}")).format(name=recipe.name)
        with self.app.commands.macro(text):
            for planned in plans:
                ids.extend(
                    self.app.commands.add_node(
                        p.record, p.parents, name=p.name, comment=p.comment, node_id=p.node_id
                    )
                    for p in planned
                )
        if plans and plans[0]:
            leaves = recipe.leaves()
            self.app.state.current = plans[0][leaves[-1] if leaves else -1].node_id
        self.applied.emit(ids)
        return ids

    def apply_to_chosen(self, recipe: Recipe) -> list[str] | None:
        """Ask for the steps to apply to (several at once)."""
        if recipe.is_import:
            return self.import_files(recipe)
        targets = self.ask_targets(recipe)
        if not targets:
            return None
        return self.apply(recipe, targets)

    def run_import(self, recipe: Recipe) -> list[str] | None:
        """An import recipe as saved (reads the file it was made from)."""
        try:
            planned = recipes.plan(recipe, registry=self.app.session.registry)
        except RecipeError as e:
            self._error(e)
            return None
        return self._add(recipe, [planned])

    def import_files(
        self, recipe: Recipe, paths: Sequence[str | pathlib.Path] | None = None
    ) -> list[str] | None:
        """An import recipe once per file: one new root (+ the recipe's steps) each."""
        if paths is None:
            from datacook.engine.formats import FormatRegistry

            exts = sorted({
                e
                for op in FormatRegistry(self.app.session.registry).readers()
                for e in getattr(op, "extensions", ())
            })
            title = str(_("All data files"))
            filters = f"{title} ({' '.join('*' + e for e in exts)})"
            paths = self.ask_paths(str(_("Apply import recipe to files")), filters)
            if not paths:
                return None
        try:
            plans = [
                recipes.plan(recipe, path=p, registry=self.app.session.registry) for p in paths
            ]
        except RecipeError as e:
            self._error(e)
            return None
        return self._add(recipe, plans)

    # --- library -----------------------------------------------------------------------
    def entries(self) -> list[recipes.LibraryEntry]:
        return self.library.entries()

    def rename(self, path: pathlib.Path, name: str | None = None) -> pathlib.Path | None:
        if name is None:
            current = recipes.load(path, self.library.registry).name
            name = self.ask_text(str(_("Rename recipe")), str(_("Name")), current)
            if not name:
                return None
        return self._library_call(self.library.update, path, name=name)

    def edit_description(
        self, path: pathlib.Path, description: str | None = None
    ) -> pathlib.Path | None:
        if description is None:
            current = recipes.load(path, self.library.registry).description
            description = self.ask_text(
                str(_("Recipe description")), str(_("Description")), current
            )
            if description is None:
                return None
        return self._library_call(self.library.update, path, description=description)

    def delete(self, paths: Sequence[pathlib.Path]) -> bool:
        if not paths:
            return False
        names = ", ".join(p.stem for p in paths)
        if not self.confirm(str(_("Delete the recipes {names}?")).format(names=names)):
            return False
        for path in paths:
            self.library.delete(path)
        self.library_changed.emit()
        return True

    def merge(self, paths: Sequence[pathlib.Path], name: str | None = None) -> pathlib.Path | None:
        return self._library_call(self.library.merge, paths, name=name)

    def import_file(self, path: str | pathlib.Path | None = None) -> pathlib.Path | None:
        """Copy a `.datacookrecipe` file into the library."""
        if path is None:
            chosen = self.ask_paths(str(_("Import recipe")), _filter())
            if not chosen:
                return None
            path = chosen[0]
        return self._library_call(self.library.import_file, path)

    def export(self, path: pathlib.Path, dest: str | pathlib.Path | None = None) -> bool:
        if dest is None:
            dest = self.ask_save_path(str(_("Export recipe")), _filter())
            if not dest:
                return False
        dest = pathlib.Path(dest)
        if dest.suffix != recipes.SUFFIX:
            dest = dest.with_name(dest.name + recipes.SUFFIX)
        try:
            recipes.load(path, self.library.registry).save(dest)
        except (RecipeError, OSError) as e:
            self._error(e)
            return False
        return True

    def _library_call(self, fn: Callable[..., pathlib.Path], *args: Any, **kwargs: Any):
        try:
            result = fn(*args, **kwargs)
        except (RecipeError, OSError) as e:
            self._error(e)
            return None
        self.library_changed.emit()
        return result

    # --- default dialogs ---------------------------------------------------------------
    def _ask_text(self, title: str, label: str, default: str) -> str | None:
        text, ok = QtWidgets.QInputDialog.getText(self.parent_widget(), title, label, text=default)
        return text.strip() if ok and text.strip() else None

    def _ask_paths(self, title: str, filters: str) -> list[str]:
        paths, _used = QtWidgets.QFileDialog.getOpenFileNames(
            self.parent_widget(), title, "", filters
        )
        return list(paths)

    def _ask_save_path(self, title: str, filters: str) -> str | None:
        path, _used = QtWidgets.QFileDialog.getSaveFileName(
            self.parent_widget(), title, "", filters
        )
        return path or None

    def _confirm(self, text: str) -> bool:
        buttons = QtWidgets.QMessageBox.StandardButton
        answer = QtWidgets.QMessageBox.question(
            self.parent_widget(), str(_("Recipes")), text, buttons.Yes | buttons.No
        )
        return answer == buttons.Yes

    def _ask_targets(self, recipe: Recipe) -> list[str] | None:
        dialog = TargetDialog(self.app, recipe, self.parent_widget())
        try:
            if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
                return None
            return dialog.targets()
        finally:
            dialog.deleteLater()


class TargetDialog(QtWidgets.QDialog):
    """Check the steps a recipe is applied to (the current step is pre-checked)."""

    def __init__(self, app: AppController, recipe: Recipe, parent: QtWidgets.QWidget | None):
        super().__init__(parent)
        from datacook.app.docks.nodetree import node_label

        self.setWindowTitle(str(_("Apply recipe {name}")).format(name=recipe.name))
        self.list = QtWidgets.QListWidget(self)
        for node in app.session.nodes():
            item = QtWidgets.QListWidgetItem(node_label(app.session, node.id))
            item.setData(PATH_ROLE, node.id)
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            checked = node.id == app.state.current
            item.setCheckState(
                QtCore.Qt.CheckState.Checked if checked else QtCore.Qt.CheckState.Unchecked
            )
            self.list.addItem(item)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(str(_("Apply to these steps:")), self))
        layout.addWidget(self.list)
        layout.addWidget(buttons)

    def targets(self) -> list[str]:
        out = []
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                out.append(str(item.data(PATH_ROLE)))
        return out


# --- dock ----------------------------------------------------------------------------------


def describe(recipe: Recipe, registry: Any) -> str:
    """HTML summary of a recipe (details pane)."""

    def title(op_id: str) -> str:
        try:
            return str(registry.get(op_id).title)
        except KeyError:
            return op_id

    kind = _("Import recipe (starts with a reader)") if recipe.is_import else _("Recipe")
    parts = [f"<b>{html.escape(recipe.name)}</b> <i>({kind})</i>"]
    if recipe.description:
        parts.append(f"<p>{html.escape(recipe.description)}</p>")
    if recipe.required_columns:
        cols = ", ".join(html.escape(c) for c in recipe.required_columns)
        label = str(_("Required columns"))
        parts.append(f"<p>{label}: {cols}</p>")
    items = []
    for step in recipe.steps:
        text = html.escape(step.name or title(step.record.op_id))
        sources = [
            str(_("input")) if ref == recipes.INPUT else str(int(ref) + 1) for ref in step.inputs
        ]
        suffix = f" <span style='color:gray'>← {', '.join(sources)}</span>" if sources else ""
        items.append(f"<li>{text}{suffix}</li>")
    parts.append(f"<ol>{''.join(items)}</ol>")
    if recipe.created:
        label = str(_("Created"))
        parts.append(f"<p style='color:gray'>{label}: {html.escape(recipe.created)}</p>")
    return "".join(parts)


class RecipesWidget(QtWidgets.QWidget):
    """Library list + details + buttons (apply, run on files, rename, merge, delete, …)."""

    def __init__(self, controller: RecipeController, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self.app = controller.app
        self.list = QtWidgets.QListWidget(self)
        self.list.setObjectName("recipe-list")
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.ActionsContextMenu)
        self.details = QtWidgets.QTextBrowser(self)
        self.details.setObjectName("recipe-details")
        self.apply_button = QtWidgets.QPushButton(self)
        self.apply_button.clicked.connect(lambda: self.apply_selected())
        self.more_button = QtWidgets.QPushButton(self)
        self.more_button.clicked.connect(lambda: self.apply_selected(choose=True))
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.more_button)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, self)
        splitter.addWidget(self.list)
        splitter.addWidget(self.details)
        splitter.setSizes([200, 200])
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        layout.addLayout(buttons)
        self._texts: dict[QtGui.QAction, object] = {}

        def action(text: object, slot: Callable[[], object]) -> QtGui.QAction:
            act = QtGui.QAction(str(text), self)
            act.triggered.connect(lambda _checked=False: slot())
            self._texts[act] = text
            self.list.addAction(act)
            return act

        self.rename_action = action(_("Rename…"), self._rename)
        self.describe_action = action(_("Edit description…"), self._describe)
        self.merge_action = action(_("Merge selected recipes"), self._merge)
        self.export_action = action(_("Export…"), self._export)
        self.delete_action = action(_("Delete"), self._delete)
        self.import_action = action(_("Import recipe file…"), controller.import_file)
        self.list.itemSelectionChanged.connect(self._on_selection)
        self.list.itemDoubleClicked.connect(lambda _item: self.apply_selected())
        controller.library_changed.connect(self.refresh)
        self.app.state.current_changed.connect(self._update_buttons)
        self.app.state.language_changed.connect(self.retranslate)
        self.retranslate()
        self.refresh()

    def retranslate(self, _language: object = None) -> None:
        for act, text in self._texts.items():
            act.setText(str(text))
        self._on_selection()

    # --- list --------------------------------------------------------------------------
    def refresh(self) -> None:
        selected = {str(p) for p in self.selected_paths()}
        self.list.clear()
        self._recipes: dict[str, Recipe] = {}
        for entry in self.controller.entries():
            item = QtWidgets.QListWidgetItem(entry.name)
            item.setData(PATH_ROLE, str(entry.path))
            if entry.recipe is None:
                item.setForeground(QtGui.QColor("#dc322f"))
                item.setToolTip(entry.error or "")
            else:
                self._recipes[str(entry.path)] = entry.recipe
                info = _("{n} steps, import") if entry.recipe.is_import else _("{n} steps")
                n = len(entry.recipe.steps)
                item.setText(f"{entry.name}  ({str(info).format(n=n)})")
            self.list.addItem(item)
            if str(entry.path) in selected:
                item.setSelected(True)
        if self.list.count() and not self.list.selectedItems():
            self.list.setCurrentRow(0)
        self._on_selection()

    def names(self) -> list[str]:
        return [
            r.name if (r := self._recipes.get(p)) else pathlib.Path(p).stem
            for p in (self.list.item(i).data(PATH_ROLE) for i in range(self.list.count()))
        ]

    def select(self, path: pathlib.Path | str) -> None:
        for row in range(self.list.count()):
            item = self.list.item(row)
            item.setSelected(item.data(PATH_ROLE) == str(path))

    def selected_paths(self) -> list[pathlib.Path]:
        if not hasattr(self, "_recipes"):
            return []
        return [pathlib.Path(i.data(PATH_ROLE)) for i in self.list.selectedItems()]

    def selected_recipe(self) -> Recipe | None:
        paths = self.selected_paths()
        return self._recipes.get(str(paths[0])) if len(paths) == 1 else None

    def _on_selection(self) -> None:
        recipe = self.selected_recipe()
        if recipe is not None:
            self.details.setHtml(describe(recipe, self.app.session.registry))
        elif not self.list.count():
            self.details.setHtml(
                "<p style='color:gray'>"
                + html.escape(
                    str(
                        _("No recipes yet. Select a step and use Steps > Recipes > Save as recipe.")
                    )
                )
                + "</p>"
            )
        else:
            self.details.clear()
        self._update_buttons()

    def _update_buttons(self, *_args: object) -> None:
        recipe = self.selected_recipe()
        n = len(self.selected_paths())
        if recipe is not None and recipe.is_import:
            self.apply_button.setText(str(_("Run")))
            self.more_button.setText(str(_("Run on files…")))
            self.apply_button.setEnabled(True)
        else:
            self.apply_button.setText(str(_("Apply to current step")))
            self.more_button.setText(str(_("Apply to steps…")))
            self.apply_button.setEnabled(recipe is not None and self.app.state.current is not None)
        self.more_button.setEnabled(recipe is not None)
        self.merge_action.setEnabled(n > 1)
        for act in (self.rename_action, self.describe_action, self.export_action):
            act.setEnabled(n == 1)
        self.delete_action.setEnabled(n > 0)

    # --- actions -----------------------------------------------------------------------
    def apply_selected(self, *, choose: bool = False) -> list[str] | None:
        recipe = self.selected_recipe()
        if recipe is None:
            return None
        if choose:
            return self.controller.apply_to_chosen(recipe)
        return self.controller.apply(recipe)

    def _one(self) -> pathlib.Path | None:
        paths = self.selected_paths()
        return paths[0] if len(paths) == 1 else None

    def _rename(self) -> None:
        if (path := self._one()) is not None and (new := self.controller.rename(path)):
            self.select(new)

    def _describe(self) -> None:
        if (path := self._one()) is not None:
            self.controller.edit_description(path)

    def _export(self) -> None:
        if (path := self._one()) is not None:
            self.controller.export(path)

    def _merge(self) -> None:
        if (new := self.controller.merge(self.selected_paths())) is not None:
            self.select(new)

    def _delete(self) -> None:
        self.controller.delete(self.selected_paths())


def create(app: AppController, window: MainWindow) -> QtWidgets.QWidget:
    controller = RecipeController(app, window)
    window.recipes = controller
    return RecipesWidget(controller)


DOCKS = (DockSpec("recipes", _("Recipes"), "right", create, tabify_with="params"),)


class RecipeMenu(QtCore.QObject):
    """Steps > Recipes submenu and the step tree's context menu entries."""

    def __init__(self, controller: RecipeController, window: MainWindow):
        super().__init__(controller)
        self.controller = controller
        self._texts: dict[QtGui.QAction, object] = {}
        self.menu = QtWidgets.QMenu(str(_("Recipes")), window)
        self.menu.setObjectName("menu-recipes")

        def action(text: object, slot: Callable[[], object]) -> QtGui.QAction:
            act = QtGui.QAction(str(text), window)
            act.triggered.connect(lambda _checked=False: slot())
            self._texts[act] = text
            self.menu.addAction(act)
            return act

        self.save_path_action = action(_("Save steps up to here as recipe…"), controller.create)
        self.save_subtree_action = action(
            _("Save step and following steps as recipe…"),
            lambda: controller.create(subtree=True),
        )
        self.menu.addSeparator()
        self.import_action = action(_("Import recipe file…"), controller.import_file)
        dock = window.docks.get("recipes")
        if dock is not None:
            self.show_action = action(_("Recipe library"), lambda: (dock.show(), dock.raise_()))
        window.menu("steps").addSeparator()
        window.menu("steps").addMenu(self.menu)
        tree = window.widgets.get("nodetree")
        extra = getattr(tree, "extra_actions", None)
        if isinstance(extra, list):
            extra.extend([self.save_path_action, self.save_subtree_action])
        controller.app.state.language_changed.connect(self.retranslate)

    def retranslate(self, _language: object = None) -> None:
        self.menu.setTitle(str(_("Recipes")))
        for act, text in self._texts.items():
            act.setText(str(text))


def install(app: AppController, window: MainWindow) -> None:
    controller = getattr(window, "recipes", None)
    if isinstance(controller, RecipeController):
        RecipeMenu(controller, window)
