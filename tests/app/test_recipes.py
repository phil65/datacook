"""App: delete a middle step keeping its children (O6), recipes dock / controller (O1)."""

from typing import TYPE_CHECKING

import pandas as pd
import pytest

from datacook.app.docks.nodetree import NodeTreeWidget
from datacook.app.docks.recipes import RecipeController, RecipesWidget
from datacook.engine import recipes
from datacook.engine.ops import columns, rows, sources
from datacook.engine.recipes import RecipeLibrary
from tests.app.conftest import check_invariant, drain


if TYPE_CHECKING:
    import pathlib

    from datacook.app.controllers import AppController
    from datacook.app.controllers.app import Message
    from datacook.app.testing import FakeSession


@pytest.fixture
def tree(qtbot, app: AppController) -> NodeTreeWidget:
    widget = NodeTreeWidget(app)
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def messages(app: AppController) -> list[Message]:
    out: list[Message] = []
    app.message_posted.connect(out.append)
    return out


@pytest.fixture
def controller(app: AppController, tmp_path: pathlib.Path) -> RecipeController:
    ctrl = RecipeController(app)
    ctrl.library = RecipeLibrary(tmp_path / "recipes", app.session.registry)
    return ctrl


def _rows(tree: NodeTreeWidget) -> list[str]:
    model = tree.model
    return ["  " * model.depth(n) + model.label(n) for n in model.ids()]


DATA = {"a": [3, 1, 2], "b": [1.0, 2.0, 3.0]}


def _source(app: AppController, name: str = "data", data: dict | None = None) -> str:
    return app.commands.add_node(sources.InlineData.record(data=data or DATA), name=name)


# --- O6 --------------------------------------------------------------------------------


def test_remove_step_keeps_children_and_undo(
    app: AppController, tree: NodeTreeWidget, fake: FakeSession
) -> None:
    root = _source(app)
    mid = app.commands.add_node(rows.SortRows.record(by=["a"]), [root], name="sort")
    c1 = app.commands.add_node(rows.Head.record(n=1), [mid], name="c1")
    app.commands.add_node(rows.Head.record(n=2), [c1], name="gc")
    app.commands.add_node(rows.Head.record(n=2), [mid], name="c2")
    app.state.current = mid
    drain(app)
    assert _rows(tree) == ["data", "  sort", "    c1", "      gc", "    c2"]
    assert tree.remove_step(mid)
    drain(app)
    assert _rows(tree) == ["data", "  c1", "    gc", "  c2"]
    assert app.state.current == c1
    assert fake[c1].parents == (root,)
    check_invariant(app)
    assert app.commands.undo_stack.undoText() == "Delete step (keep following steps)"
    app.commands.undo()
    drain(app)
    assert fake[c1].parents == (mid,)
    assert _rows(tree) == ["data", "  sort", "    c1", "      gc", "    c2"]
    app.commands.redo()
    drain(app)
    assert _rows(tree) == ["data", "  c1", "    gc", "  c2"]
    check_invariant(app)


def test_remove_step_refused_for_source(
    app: AppController, tree: NodeTreeWidget, messages: list[Message]
) -> None:
    root = _source(app)
    app.commands.add_node(rows.Head.record(n=1), [root])
    drain(app)
    n = app.commands.undo_stack.count()
    assert not tree.remove_step(root)
    assert messages[-1].level == "error"
    assert "first step" in messages[-1].text
    assert app.commands.undo_stack.count() == n  # nothing on the stack
    assert root in app.session


def test_tree_context_menu_has_both_deletes(tree: NodeTreeWidget) -> None:
    texts = [act.text() for act, _t in tree._actions]
    i = texts.index("Delete step")
    assert texts[i + 1] == "Delete step (keep following steps)"


# --- O1 --------------------------------------------------------------------------------


def _recipe_from_subtree(app: AppController, controller: RecipeController, fake: FakeSession):
    root = _source(app)
    sel = app.commands.add_node(columns.SelectColumns.record(columns=["a"]), [root], name="pick")
    app.commands.add_node(rows.SortRows.record(by=["a"]), [sel])
    fake.put(root, pd.DataFrame(DATA))
    path = controller.create(sel, subtree=True, name="Pick and sort")
    assert path is not None
    return root, recipes.load(path)


def test_create_and_apply_recipe_with_undo(
    app: AppController, controller: RecipeController, fake: FakeSession
) -> None:
    _root, recipe = _recipe_from_subtree(app, controller, fake)
    assert recipe.required_columns == ("a",)
    other = _source(app, "other")
    fake.put(other, pd.DataFrame({"a": [5], "z": [1]}))
    n_nodes, n_undo = len(fake), app.commands.undo_stack.count()
    ids = controller.apply(recipe, [other])
    assert ids is not None
    assert len(ids) == 2
    assert fake[ids[0]].parents == (other,)
    assert fake[ids[0]].name == "pick"
    assert app.state.current == ids[-1]
    assert app.commands.undo_stack.count() == n_undo + 1  # one macro
    app.commands.undo()
    assert len(fake) == n_nodes
    app.commands.redo()
    assert len(fake) == n_nodes + 2
    drain(app)
    check_invariant(app)


def test_apply_missing_column_notifies(
    app: AppController,
    controller: RecipeController,
    fake: FakeSession,
    messages: list[Message],
) -> None:
    _root, recipe = _recipe_from_subtree(app, controller, fake)
    wrong = _source(app, "wrong", {"x": [1]})
    fake.put(wrong, pd.DataFrame({"x": [1]}))
    n = len(fake)
    assert controller.apply(recipe, [wrong]) is None
    assert len(fake) == n
    assert messages[-1].level == "error"
    assert "'wrong'" in messages[-1].text
    assert "a" in messages[-1].text


def test_apply_to_several_steps(
    app: AppController, controller: RecipeController, fake: FakeSession
) -> None:
    _root, recipe = _recipe_from_subtree(app, controller, fake)
    targets = [_source(app, f"t{i}") for i in range(3)]
    for t in targets:
        fake.put(t, pd.DataFrame(DATA))
    controller.ask_targets = lambda _recipe: targets
    ids = controller.apply_to_chosen(recipe)
    assert ids is not None
    assert len(ids) == 6
    assert {fake[i].parents[0] for i in ids[::2]} == set(targets)
    n = len(fake)
    app.commands.undo()
    assert len(fake) == n - 6


def test_apply_computes_unknown_targets_first(
    qtbot,
    app: AppController,
    controller: RecipeController,
    fake: FakeSession,
    messages: list[Message],
) -> None:
    _root, recipe = _recipe_from_subtree(app, controller, fake)
    other = _source(app, "other")  # not computed yet: columns unknown
    assert controller.apply(recipe, [other]) is None
    assert app.jobs.is_running("recipe-check")

    def finished() -> bool:
        drain(app)
        return not app.jobs.is_running("recipe-check")

    qtbot.waitUntil(finished, timeout=2000)
    # the FakeSession computes nothing: the check fails with a message, nothing is added
    assert messages[-1].level == "error"
    assert "check the columns" in messages[-1].text
    # once computed, the same call applies directly
    fake.put(other, pd.DataFrame(DATA))
    assert controller.apply(recipe, [other]) is not None


def test_import_recipe_on_three_csv_files(
    app: AppController, controller: RecipeController, tmp_path: pathlib.Path, fake: FakeSession
) -> None:
    files = []
    for i in range(3):
        path = tmp_path / f"f{i}.csv"
        pd.DataFrame({"a": [i]}).to_csv(path, index=False)
        files.append(str(path))
    root = app.commands.add_node(sources.ReadCsv.record(path=files[0]))
    srt = app.commands.add_node(rows.SortRows.record(by=["a"]), [root])
    path = controller.create(srt, name="Import")
    assert path is not None
    recipe = recipes.load(path)
    assert recipe.is_import
    controller.ask_paths = lambda _title, _filters: files
    n = len(fake)
    ids = controller.apply_to_chosen(recipe)  # import recipe: asks for files
    assert ids is not None
    assert len(ids) == 6
    readers = [fake[i] for i in ids[::2]]
    assert [r.record.params.path for r in readers] == files  # ty: ignore[unresolved-attribute]
    assert [r.name for r in readers] == ["f0.csv", "f1.csv", "f2.csv"]
    app.commands.undo()
    assert len(fake) == n


def test_recipes_widget_library_actions(
    qtbot, app: AppController, controller: RecipeController, fake: FakeSession
) -> None:
    widget = RecipesWidget(controller)
    qtbot.addWidget(widget)
    assert widget.names() == []
    root, _recipe = _recipe_from_subtree(app, controller, fake)
    assert widget.names() == ["Pick and sort"]
    path = widget.selected_paths()[0]
    assert "Required columns" in widget.details.toPlainText()
    # rename + merge with a copy + delete
    controller.ask_text = lambda _t, _l, _d: "Renamed"
    widget._rename()
    assert widget.names() == ["Renamed"]
    copy = controller.library.save(recipes.load(widget.selected_paths()[0]))
    widget.refresh()
    for row in range(widget.list.count()):
        widget.list.item(row).setSelected(True)
    assert widget.merge_action.isEnabled()
    widget._merge()
    assert "Renamed + Renamed" in widget.names()
    assert len(recipes.load(widget.selected_paths()[0]).steps) == 4
    controller.confirm = lambda _text: True
    widget.select(copy)
    widget._delete()
    assert len(widget.names()) == 2
    assert not path.exists()  # renamed away
    # apply the selected recipe to the current step
    renamed = next(e.path for e in controller.entries() if e.name == "Renamed")
    widget.select(renamed)
    app.state.current = root
    assert widget.apply_button.isEnabled()
    ids = widget.apply_selected()
    assert ids is not None
    assert fake[ids[0]].parents == (root,)
