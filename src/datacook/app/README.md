# datacook.app: core API for docks and widgets

Design: `DATACOOK_APP_DESIGN.md` (owner's OSS workspace). This file lists what a dock /
widget uses. Rule of thumb: **docks own widgets only**; they read the session, `AppState`
and the view slots, write `AppState` and call controllers. They never call
`Session.add/update/remove/pin/unpin` and never hold a full frame of their own.

## Registering a dock (no shared file to edit)

`uimodules.UI_MODULES` already lists every planned module (`docks.dataview`,
`docks.nodetree`, `docks.code`, `widgets.memoryindicator`, `docks.params`, `actions`,
`controllers.project`, `docks.schema`, `docks.messages`, `docks.recipes`). Missing modules are skipped, so a
work package only creates its module. A module may define:

```python
from datacook.app.uimodules import DockSpec
from datacook.i18n import _


def create(app: AppController, window: MainWindow) -> QWidget: ...


DOCKS = (DockSpec("nodetree", _("Steps"), "left", create),)
# area: "left" | "right" | "bottom" | "central" | "status"; tabify_with="<dock id>"


def install(app: AppController, window: MainWindow) -> None:
    """Optional; runs after all docks exist: menus, toolbar, shortcuts."""
    window.menu("file").addAction(...)  # keys: file, edit, view, steps, help
```

`window.docks[id]` (QDockWidget), `window.widgets[id]` (what `create` returned). Dock titles
are re-read with `str(spec.title)` on `app.state.language_changed`; a dock widget with own
texts connects to that signal itself (`retranslate()`).

## Modules (what each WP added)

| Module | What | Hooks / API for tests and other docks |
|---|---|---|
| `docks/nodetree.py` | Steps tree (`NodeTreeModel`: ids + structure only; badges, shape, size); rename (F2), comment, branch, delete (Del), delete one step keeping the following steps (Shift+Del) | `widget.model.index_of(id)`, `widget.view`, `widget.remove_step(id)`, `widget.extra_actions` (more context menu entries) |
| `docks/dataview.py` | central data view: one `DataFrameViewer` per slot ("node", "preview"), overlays for slot states, display-only sort (permutation on the view pool), "Add as sort step" | `view.page`, `view.viewer`, `view.is_sorting()`, `view.add_sort_step()` |
| `docks/code.py` | code pane (`CodeController`: one render per event-loop turn, span of the current step highlighted, error markers) | `pane.editor` |
| `widgets/memoryindicator.py` | status bar: cache / budget / RSS, menu of cached steps, "Free memory" | — |
| `widgets/overlay.py` | translucent message panel with buttons (slot states) | — |
| `docks/params.py` | `ParamsPanel`: `PydanticForm` of the open preview (column editors from `widgets/columnchooser.py`), live preview, Apply / Cancel | `panel.form.set_value()`, `panel.apply()`, `panel.cancel()` |
| `actions.py` | `OpActions` (object name `op-actions`): one `QAction` per op (`op-<id>`), Steps menu by category, command palette (Ctrl+Shift+P), Edit step (Ctrl+E), Cancel preview (Esc) | `ops.start(op_id)`, `ops.choose_input` (second input of a merge) |
| `controllers/project.py` | `ProjectController` (`window.project`): New / Open / Save (As), recent files, Open data (`widgets/readerdialog.py`), exports (CSV / Parquet / Excel / script), unsaved-changes prompt on close, window title | dialog hooks: `ask_open_path`, `ask_save_path`, `confirm_discard`, `ask_save_changes`, `exec_dialog`, `ask_writer_params` |
| `docks/schema.py` | Columns dock: `SchemaModel` of the displayed slot, column statistics on the view pool, categories; a hint while no column is selected | `widget.profile`, `widget.hint` |
| `docks/messages.py` | Messages dock: `app.notify()`, failing steps, `datacook` log records; View > Language (`application.LanguageMenu`) | — |
| `docks/recipes.py` | Recipes dock (right, tab with Parameters) + Steps > Recipes: `RecipeController` (`window.recipes`): save a step path / subtree as recipe, apply to the current or chosen steps (required columns checked first; unknown schemas computed on the view pool, slot "recipe-check"), run an import recipe / on files, library (rename, description, delete, merge, import, export); one undo macro per apply | `controller.create()`, `apply(recipe, targets)`, `apply_to_chosen()`, `import_files()`, `library` (`engine.recipes.RecipeLibrary`); hooks `ask_text`, `ask_paths`, `ask_save_path`, `ask_targets`, `confirm` |
| `application.py` | `create_window()`, `main()` (`datacook [project \| data file]`), `set_language()` / `choose_language()` | `open_paths(window, paths)` |

The first dock of a tab group is the visible tab (Code before Messages, Parameters before
Columns). Initial dock sizes: `mainwindow.DOCK_SIZES`.

## Language switch (`application.py`)

`set_language(app, code | None)` switches the gettext catalog, Qt's `QTranslator` (qtbase)
and `app.state.language`; `choose_language(app, code | None)` also stores the choice in the
settings file (`None` = system language). View > Language (`LanguageMenu`, installed by
`docks.messages`) calls it and `retranslate()`s every `PydanticForm` in the window; other
widgets with own texts connect to `app.state.language_changed`. Give cutepandas models /
widgets `translate=datacook.i18n.translate`.

## `app: AppController` (`controllers/app.py`)

| Attribute | What |
|---|---|
| `app.session` | `SessionLike` (engine `Session`): `get`, `nodes`, `roots`, `children`, `ancestors`, `descendants`, `summary`, `error`, `memory`, `is_cached`, `render_code` — lock-protected, cheap on the GUI thread. Read only. |
| `app.state` | `AppState` (below) |
| `app.bridge` | `SessionBridge`: GUI-thread signals for engine events |
| `app.commands` | `CommandController`: every mutation, undoable |
| `app.nodes` | `NodeController`: `nodes.slot` = the "current" `ViewSlot`; `recompute()` |
| `app.preview` | `PreviewController`: `preview.slot` = the "preview" `ViewSlot` |
| `app.jobs` | `JobRunner`: `running_ids()`, `submit_view(slot, fn, *args, on_done=)` (view pool) |
| `app.pins` | `PinBook`: `pinned_ids()` (tree badge "pinned") |
| `app.held_ids()` | nodes whose full frame a view holds (invariant: ⊆ `pins.pinned_ids()`) |
| `app.free_memory()` | drop every unpinned cached frame (memory indicator "Free memory") |
| `app.notify(text, level, node_id)` | user message -> `message_posted(Message)` (messages dock) |
| `app.new_project()` | empty tree + undo history (project controller) |
| signals | `jobs_changed()` (job indicator, "computing" badges), `message_posted(Message)` |

## `app.state: AppState` (`state.py`, GUI thread)

Properties with a `<name>_changed` signal, emitted only on a real change:
`current` (node id; `current_changed(old, new)`), `column`, `preview` (`PreviewSpec`: mode
`add|edit`, `op_id`, `target`, `inputs`, `params`), `display` (`"node" | "preview"`: what the
data view and schema dock show), `sort` (`SortSpec(column, descending)`: display-only sort,
reset on selection change), `settings` (`AppSettings`, `update_settings(**changes)`),
`language` (`language_changed`: retranslate).

## `app.bridge: SessionBridge` (`bridge.py`)

Signals (tuples of ids, coalesced per event-loop turn, events of outdated generations
dropped): `nodes_added`, `nodes_removed` (incl. descendants; may name ids a view never saw),
`nodes_changed` (params / name / comment), `nodes_moved` (new parents: a middle step was
deleted or restored; `nodes_invalidated` follows), `nodes_invalidated`, `nodes_materialized`,
`nodes_evicted`, `node_error(id, exc)` (the failing step), `memory_changed()`,
`structure_reset()` (> 200 events at once: rebuild from `session.nodes()`), `drained()`.
`bridge.post(fn, *args)` runs `fn` on the GUI thread (any thread may call it).

## View slots (`slots.py`)

`ViewSlot.holder` is a long-lived cutepandas `DataFrameHolder`: bind a viewer / models to it
once (`DataFrameViewer(app.nodes.slot.holder)`), never call `holder.set_df` yourself.
`slot.state_changed(state)`; `slot.state` (`SlotState`: `empty`, `loading`, `ready`, `stale`,
`evicted`, `error`), `node_id`, `generation`, `summary` (last known shape for overlays),
`error`, `error_node` (failing step, may be an ancestor: "Go to step"), `message` (overlay text,
e.g. "computing full result…"). The data view shows `app.nodes.slot` or `app.preview.slot`
depending on `app.state.display`.

## `app.commands: CommandController` (`controllers/command.py`)

`add_node(record, parents=(), name=, comment=, node_id=) -> id` (root, step or branch), `remove_subtree(id)`,
`remove_step(id)` (delete one step, its children move to its parent; raises
`engine.restructure.StepError` with a translated reason for sources / merges / missing columns),
`edit_params(id, record)`, `rename(id, name)`, `set_comment(id, text)` (consecutive edits merge),
`with macro(text):` (one undo step), `undo()`, `redo()`, `clear()`, `is_clean()` / `set_clean()`
(saved state), `undo_stack` (`createUndoAction` / `createRedoAction`; the main window already
has Undo / Redo in the Edit menu). A failing command raises and is not put on the stack.
After `add_node`, select the new node with `app.state.current = id` if wanted.

## `app.preview: PreviewController` (`controllers/preview.py`)

`start_add(op_id, inputs, params=None)` (readers: `inputs=()`), `start_edit(node_id)`,
`set_params(params | None)` from the form's (debounced) value signal, `commit() -> id`,
`cancel()`, signal `committed(id)`. The form follows `app.state.preview_changed` (e.g. reload
after undo changed the edited step). Previews are not on the undo stack.

## Testing

`datacook.app.testing.FakeSession` (Qt-free): requests stay pending until
`fake.complete(req, frame)` / `fake.fail(req, exc, failing=)`; `fake.put(id, frame)` caches a
frame, `fake.evict(*ids)`, `fake.pending(id)`, `fake.pending_previews()`, `fake.pin_counts()`.
`tests/app/conftest.py`: `app` fixture (`AppController(FakeSession)`, debounce 0), `drain(app)`
(deliver the bridge queue), `check_invariant(app)`. Qt-free modules (`protocols`, `settings`,
`pins`, `eventqueue`, `jobs`, `testing`) are tested in `tests/test_app_core.py`, which also runs
in the free-threaded CI job. `tests/app/test_smoke.py` drives the real `MainWindow` with every
module (reader dialog, ops via actions + form, branch, preview edit, undo / redo, display sort,
script export run in a subprocess, save / open); `DATACOOK_MEMORY_SCENARIO=1` adds a 3M-row
memory scenario.
