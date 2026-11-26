"""Bridge across threads, commands, the real engine behind the controllers, MainWindow shell."""

import sys
import threading
import types
from typing import TYPE_CHECKING

import pandas as pd
from prettyqt.qt import QtWidgets
import pytest

from datacook.app.bridge import SessionBridge
from datacook.app.controllers import AppController
from datacook.app.mainwindow import MainWindow
from datacook.app.settings import AppSettings
from datacook.app.slots import SlotState
from datacook.app.uimodules import DockSpec, load_modules
from datacook.engine.ops import rows, sources
from tests.app.conftest import check_invariant, drain


if TYPE_CHECKING:
    from collections.abc import Iterator

    from datacook.app.testing import FakeSession


# --- bridge ------------------------------------------------------------------------------


def test_bridge_marshals_worker_events_to_gui_thread(qtbot, fake: FakeSession) -> None:
    bridge = SessionBridge(fake)
    root = fake.add(sources.InlineData.record(data={"a": [1]})).id
    req = fake.request(root)
    seen: list[tuple[str, bool]] = []
    gui = threading.get_ident()
    bridge.nodes_materialized.connect(
        lambda _ids: seen.append(("materialized", threading.get_ident() == gui))
    )
    req.add_done_callback(
        lambda _r: bridge.post(lambda: seen.append(("done", threading.get_ident() == gui)))
    )
    worker = threading.Thread(target=fake.complete, args=(req, pd.DataFrame({"a": [1]})))
    worker.start()
    worker.join()
    assert seen == []  # nothing ran on the worker
    qtbot.waitUntil(lambda: len(seen) == 2, timeout=2000)
    assert seen == [("materialized", True), ("done", True)]
    bridge.close()


def test_bridge_coalesces_one_drain(qtbot, fake: FakeSession) -> None:
    bridge = SessionBridge(fake)
    added: list[tuple[str, ...]] = []
    memory: list[bool] = []
    bridge.nodes_added.connect(added.append)
    bridge.memory_changed.connect(lambda: memory.append(True))
    ids = [fake.add(sources.InlineData.record(data={"a": [i]})).id for i in range(5)]
    with qtbot.waitSignal(bridge.drained, timeout=2000):
        pass
    assert added == [tuple(ids)]
    assert memory == [True]
    resets: list[bool] = []
    bridge.structure_reset.connect(lambda: resets.append(True))
    for i in range(250):
        fake.add(sources.InlineData.record(data={"a": [i]}))
    bridge.flush()
    assert resets == [True]
    bridge.close()


# --- commands ----------------------------------------------------------------------------


def test_failed_command_is_not_on_stack(app: AppController) -> None:
    with pytest.raises(KeyError, match="unknown parent"):
        app.commands.add_node(rows.Head.record(), ["missing"])
    assert not app.commands.can_undo()
    assert app.commands.undo_stack.count() == 0


def test_rename_merges_consecutive_edits(app: AppController, fake: FakeSession) -> None:
    root = app.commands.add_node(sources.InlineData.record(data={"a": [1]}))
    app.commands.rename(root, "x")
    app.commands.rename(root, "xy")
    app.commands.set_comment(root, "note")
    assert app.commands.undo_stack.count() == 3  # add, rename (merged), comment
    app.commands.undo()
    app.commands.undo()
    node = fake.get(root)
    assert node is not None
    assert node.name is None
    assert node.comment is None


def test_macro_is_one_undo_step(app: AppController, fake: FakeSession) -> None:
    with app.commands.macro("import"):
        root = app.commands.add_node(sources.InlineData.record(data={"a": [1]}))
        app.commands.add_node(rows.Head.record(n=1), [root])
    assert len(fake) == 2
    app.commands.undo()
    assert len(fake) == 0


# --- real engine -------------------------------------------------------------------------


@pytest.fixture
def real_app(qapp) -> Iterator[AppController]:
    controller = AppController(settings=AppSettings(selection_debounce_ms=0, preview_rows=2))
    yield controller
    session = controller.session
    controller.close()
    assert session.memory().pinned_nodes == 0


def test_real_engine_select_preview_commit(qtbot, real_app: AppController) -> None:
    app = real_app
    data = {"k": [3, 1, 2, 5, 4], "s": list("abcde")}
    root = app.commands.add_node(sources.InlineData.record(data=data))
    sort = app.commands.add_node(rows.SortRows.record(by=["k"]), [root])
    app.state.current = sort
    qtbot.waitUntil(lambda: app.nodes.slot.state == SlotState.READY, timeout=5000)
    shown = app.nodes.slot.frame
    assert shown is not None
    assert list(shown["k"]) == [1, 2, 3, 4, 5]
    assert shown is app.session.materialize(sort)  # the cached frame itself
    check_invariant(app)

    app.preview.start_add("head", [sort], rows.Head.Params(n=3))
    qtbot.waitUntil(lambda: app.state.display == "preview", timeout=5000)
    head = app.preview.slot.frame
    assert head is not None
    assert len(head) == 2  # preview_rows
    new = app.preview.commit()
    assert new is not None
    qtbot.waitUntil(lambda: app.state.display == "node", timeout=5000)
    frame = app.nodes.slot.frame
    assert frame is not None
    assert len(frame) == 3
    assert app.pins.owned("current") == (new, sort)
    check_invariant(app)


def test_real_engine_error_and_undo(qtbot, real_app: AppController) -> None:
    app = real_app
    root = app.commands.add_node(sources.InlineData.record(data={"k": [1, 2]}))
    bad = app.commands.add_node(rows.SortRows.record(by=["missing"]), [root])
    child = app.commands.add_node(rows.Head.record(n=1), [bad])
    app.state.current = child
    qtbot.waitUntil(lambda: app.nodes.slot.state == SlotState.ERROR, timeout=5000)
    assert app.nodes.slot.error_node == bad
    app.commands.edit_params(bad, rows.SortRows.record(by=["k"]))
    qtbot.waitUntil(lambda: app.nodes.slot.state == SlotState.READY, timeout=5000)
    app.commands.undo()
    qtbot.waitUntil(lambda: app.nodes.slot.state == SlotState.ERROR, timeout=5000)


# --- main window -------------------------------------------------------------------------


def _install_fake_module(name: str) -> types.ModuleType:
    module = types.ModuleType(name)

    def tree(_app: AppController, _window: MainWindow) -> QtWidgets.QWidget:
        return QtWidgets.QLabel("tree")

    def schema(_app: AppController, _window: MainWindow) -> QtWidgets.QWidget:
        return QtWidgets.QLabel("schema")

    def params(_app: AppController, _window: MainWindow) -> QtWidgets.QWidget:
        return QtWidgets.QLabel("params")

    def central(_app: AppController, _window: MainWindow) -> QtWidgets.QWidget:
        return QtWidgets.QLabel("data")

    def install(_app: AppController, window: MainWindow) -> None:
        window.menu("file").addAction("Open")

    module.DOCKS = (  # ty: ignore[unresolved-attribute]
        DockSpec("tree", "Steps", "left", tree),
        DockSpec("params", "Parameters", "right", params),
        DockSpec("schema", "Schema", "right", schema, tabify_with="params"),
        DockSpec("data", "Data", "central", central),
    )
    module.install = install  # ty: ignore[unresolved-attribute]
    sys.modules[name] = module
    return module


def test_mainwindow_builds_registered_docks(qtbot, app: AppController) -> None:
    name = "datacook_test_fake_dock_module"
    _install_fake_module(name)
    try:
        window = MainWindow(app, modules=(name, "datacook.app.docks.not_written_yet"))
        qtbot.addWidget(window)
    finally:
        del sys.modules[name]
    assert set(window.docks) == {"tree", "params", "schema"}
    assert window.tabifiedDockWidgets(window.docks["params"]) == [window.docks["schema"]]
    assert isinstance(window.centralWidget(), QtWidgets.QLabel)
    assert window.widgets["data"] is window.centralWidget()
    assert [a.text() for a in window.menu("file").actions()] == ["Open"]
    assert window.windowTitle() == "Untitled - DataCook"
    app.commands.add_node(sources.InlineData.record(data={"a": [1]}))
    assert window.windowTitle() == "Untitled* - DataCook"
    window.close()


def test_mainwindow_default_modules(qtbot, app: AppController) -> None:
    window = MainWindow(app)
    qtbot.addWidget(window)
    assert window.centralWidget() is not None
    assert window.undo_action.isEnabled() is False
    # the first dock of a tab group is the visible tab: Code (bottom), Parameters (right)
    window.show()
    qtbot.waitExposed(window)
    assert not window.docks["code"].visibleRegion().isEmpty()
    assert window.docks["messages"].visibleRegion().isEmpty()
    assert not window.docks["params"].visibleRegion().isEmpty()
    assert window.docks["schema"].visibleRegion().isEmpty()


def test_load_modules_skips_missing_raises_broken(tmp_path, monkeypatch) -> None:
    assert load_modules(("datacook.app.docks.does_not_exist",)) == []
    (tmp_path / "datacook_test_broken_ui.py").write_text("import datacook_no_such_dep\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(ModuleNotFoundError, match="datacook_no_such_dep"):
        load_modules(("datacook_test_broken_ui",))


def test_drain_helper_settles(app: AppController) -> None:
    app.commands.add_node(sources.InlineData.record(data={"a": [1]}))
    drain(app)
    assert app.bridge.pending() == 0


def test_language_switch_retranslates_shell(qtbot, app: AppController) -> None:
    from datacook.app.application import set_language

    window = MainWindow(app, modules=())
    qtbot.addWidget(window)
    try:
        set_language(app, "de")
        assert window.menu("view").title() == "&Ansicht"
    finally:
        set_language(app, None)
    assert window.menu("view").title() == "&View"
