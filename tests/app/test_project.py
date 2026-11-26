"""ProjectController on the real engine: project round trip, reader dialog, exports."""

from typing import TYPE_CHECKING

import pandas as pd
import pytest

from datacook.app.controllers import AppController
from datacook.app.controllers.project import ProjectController
from datacook.app.mainwindow import MainWindow
from datacook.app.settings import AppSettings
from datacook.app.slots import SlotState
from datacook.app.widgets.readerdialog import ReaderDialog
from datacook.engine import parser
from datacook.engine.formats import WriteCsv
from datacook.engine.ops import rows, sources
from tests.app.conftest import check_invariant


if TYPE_CHECKING:
    from collections.abc import Iterator
    import pathlib

    from prettyqt.qt import QtWidgets


DATA = pd.DataFrame({"a": [3, 1, 2, 5], "b": ["x", "y", "z", "w"]})


@pytest.fixture
def real_app(qapp) -> Iterator[AppController]:
    settings = AppSettings(selection_debounce_ms=0, preview_debounce_ms=0, preview_rows=10)
    controller = AppController(settings=settings)
    yield controller
    controller.close()


@pytest.fixture
def ctl(real_app: AppController) -> ProjectController:
    return ProjectController(real_app)


@pytest.fixture
def csv_file(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "data.csv"
    DATA.to_csv(path, index=False)
    return path


def _snapshot(app: AppController) -> list[tuple[object, ...]]:
    return [(n.id, n.record, n.parents, n.name, n.comment) for n in app.session.nodes()]


def test_project_save_new_open_round_trip(
    real_app: AppController, ctl: ProjectController, tmp_path: pathlib.Path
) -> None:
    app = real_app
    root = app.commands.add_node(sources.InlineData.record(data={"a": [3, 1, 2]}), name="raw")
    app.commands.add_node(rows.SortRows.record(by=["a"]), [root])
    branch = app.commands.add_node(rows.Head.record(n=2), [root])
    app.commands.set_comment(branch, "first two")
    assert ctl.dirty
    before = _snapshot(app)
    path = tmp_path / "project.datacook"
    assert ctl.save_as(path)
    assert not ctl.dirty
    assert ctl.path == path
    assert ctl.new()
    assert len(app.session) == 0
    assert ctl.path is None
    assert ctl.open(path)
    assert _snapshot(app) == before
    assert not ctl.dirty
    assert not app.commands.can_undo()
    assert app.state.current == before[-1][0]
    assert ctl.recent_files()[0] == str(path)


def test_unsaved_changes_ask_before_discarding(
    real_app: AppController, ctl: ProjectController, tmp_path: pathlib.Path
) -> None:
    real_app.commands.add_node(sources.InlineData.record(data={"a": [1]}))
    asked: list[bool] = []

    def refuse() -> bool:
        asked.append(True)
        return False

    ctl.confirm_discard = refuse
    assert not ctl.new()
    assert len(real_app.session) == 1
    assert asked == [True]
    ctl.confirm_discard = lambda: True
    assert ctl.new()
    assert len(real_app.session) == 0


def test_open_invalid_project_reports_error(
    real_app: AppController, ctl: ProjectController, tmp_path: pathlib.Path
) -> None:
    path = tmp_path / "broken.datacook"
    path.write_text('{"format": "something else"}')
    messages = []
    real_app.message_posted.connect(messages.append)
    assert not ctl.open(path)
    assert messages[-1].level == "error"
    assert len(real_app.session) == 0


def test_reader_dialog_previews_and_adds_root(
    real_app: AppController, ctl: ProjectController, csv_file: pathlib.Path, qtbot
) -> None:
    assert "*.csv" in ctl.reader_filters()
    shown: list[pd.DataFrame] = []

    def run(dialog: QtWidgets.QDialog) -> bool:
        assert isinstance(dialog, ReaderDialog)
        qtbot.waitUntil(lambda: dialog.viewer.holder.df is not None, timeout=5000)
        shown.append(dialog.viewer.holder.df)
        return True

    ctl.exec_dialog = run
    node_id = ctl.open_data(csv_file)
    assert node_id is not None
    assert list(shown[0].columns) == ["a", "b"]
    assert len(shown[0]) == len(DATA)
    node = real_app.session.get(node_id)
    assert node is not None
    assert node.op_id == "read_csv"
    assert node.record.params.path == str(csv_file)  # ty: ignore[unresolved-attribute]
    assert real_app.state.current == node_id
    qtbot.waitUntil(lambda: real_app.nodes.slot.state == SlotState.READY, timeout=5000)
    check_invariant(real_app)
    real_app.commands.undo()
    assert node_id not in real_app.session


def test_open_data_unknown_format(real_app: AppController, ctl: ProjectController) -> None:
    messages = []
    real_app.message_posted.connect(messages.append)
    assert ctl.open_data("table.unknownext") is None
    assert messages[-1].level == "error"


def test_export_script_reproduces_frame(
    real_app: AppController, ctl: ProjectController, csv_file: pathlib.Path, tmp_path, qtbot
) -> None:
    app = real_app
    root = app.commands.add_node(sources.ReadCsv.record(path=str(csv_file)))
    step = app.commands.add_node(rows.FilterRows.record(expr="a > 1"), [root])
    leaf = app.commands.add_node(rows.SortRows.record(by=["a"], ascending=False), [step])
    app.state.current = leaf
    qtbot.waitUntil(lambda: app.nodes.slot.state == SlotState.READY, timeout=5000)
    script = tmp_path / "script.py"
    assert ctl.export_script(script)
    text = script.read_text()
    namespace: dict = {}
    exec(text, namespace)
    last = parser.parse(text, app.session.registry).steps[-1].output
    pd.testing.assert_frame_equal(namespace[last], app.session.materialize(leaf))


def test_export_data_csv(
    real_app: AppController, ctl: ProjectController, tmp_path: pathlib.Path, qtbot
) -> None:
    app = real_app
    root = app.commands.add_node(sources.InlineData.record(data={"a": [1, 2], "b": ["x", "y"]}))
    app.state.current = root
    target = tmp_path / "out.csv"
    with qtbot.waitSignal(ctl.exported, timeout=5000):
        assert ctl.export_data("csv", target, WriteCsv.Params())
    assert pd.read_csv(target).to_dict("list") == {"a": [1, 2], "b": ["x", "y"]}


def test_file_menu_entries(real_app: AppController, qtbot) -> None:
    window = MainWindow(real_app, modules=("datacook.app.controllers.project",))
    qtbot.addWidget(window)
    texts = [a.text() for a in window.menu("file").actions() if a.text()]
    assert texts[:5] == [
        "&New project",
        "&Open project…",
        "Open &recent",
        "&Save project",
        "Save project &as…",
    ]
    assert window.findChild(ProjectController) is not None
    window.close()


def test_writer_params_dialog(real_app: AppController, ctl: ProjectController) -> None:
    ctl.exec_dialog = lambda _dialog: True
    assert ctl.ask_writer_params(WriteCsv) == WriteCsv.Params()
    ctl.exec_dialog = lambda _dialog: False
    assert ctl.ask_writer_params(WriteCsv) is None


def test_window_title_shows_project_and_dirty_marker(
    real_app: AppController, tmp_path: pathlib.Path, qtbot
) -> None:
    window = MainWindow(real_app, modules=("datacook.app.controllers.project",))
    qtbot.addWidget(window)
    ctl = window.project
    assert isinstance(ctl, ProjectController)
    assert window.windowTitle() == "Untitled - DataCook"
    real_app.commands.add_node(sources.InlineData.record(data={"a": [1]}))
    assert window.windowTitle() == "Untitled* - DataCook"
    assert ctl.save_as(tmp_path / "demo.datacook")
    assert window.windowTitle() == "demo.datacook - DataCook"
    real_app.commands.undo()
    assert window.windowTitle() == "demo.datacook* - DataCook"
    ctl.confirm_discard = lambda: True
    assert ctl.new()
    assert window.windowTitle() == "Untitled - DataCook"
    ctl.ask_save_changes = pytest.fail  # clean: closes without asking
    assert window.close()


@pytest.mark.parametrize(
    ("choice", "closes", "saved"),
    [("cancel", False, False), ("discard", True, False), ("save", True, True)],
)
def test_close_asks_to_save_unsaved_changes(
    real_app: AppController, tmp_path: pathlib.Path, qtbot, choice, closes, saved
) -> None:
    window = MainWindow(real_app, modules=("datacook.app.controllers.project",))
    qtbot.addWidget(window)
    ctl = window.project
    assert isinstance(ctl, ProjectController)
    target = tmp_path / "p.datacook"
    ctl.ask_save_path = lambda _title, _filters: str(target)
    asked: list[bool] = []

    def ask() -> str:
        asked.append(True)
        return choice

    ctl.ask_save_changes = ask  # ty: ignore[invalid-assignment]
    window.show()
    real_app.commands.add_node(sources.InlineData.record(data={"a": [1]}))
    assert window.close() is closes
    assert asked == [True]
    assert target.exists() is saved


def test_late_teardown_does_not_touch_the_deleted_undo_stack(real_app, qtbot) -> None:
    """QUndoStack's destructor emits cleanChanged; the title must not query the stack."""
    import shiboken6

    window = MainWindow(real_app, modules=())
    qtbot.addWidget(window)
    real_app.commands.add_node(sources.InlineData.record(data={"a": [1]}))
    assert window.windowTitle().startswith("Untitled*")
    shiboken6.delete(real_app.commands)  # deletes the stack (dirty -> cleanChanged)
    assert window.windowTitle() == "Untitled - DataCook"


def test_command_line_paths(real_app: AppController, tmp_path, csv_file, qtbot) -> None:
    from datacook.app.application import open_paths

    window = MainWindow(real_app, modules=("datacook.app.controllers.project",))
    qtbot.addWidget(window)
    ctl = window.project
    assert isinstance(ctl, ProjectController)
    root = real_app.commands.add_node(sources.InlineData.record(data={"a": [1]}), name="raw")
    target = tmp_path / "cli.datacook"
    assert ctl.save_as(target)
    assert ctl.new()
    opened: list[object] = []
    ctl.open_data = lambda path=None: opened.append(path)  # ty: ignore[invalid-assignment]
    open_paths(window, [str(target), str(csv_file)])
    assert [n.id for n in real_app.session.nodes()] == [root]
    assert window.windowTitle() == "cli.datacook - DataCook"
    assert opened == [str(csv_file)]
