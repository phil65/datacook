"""Op actions: palette and Steps menu from the registry, starting previews, language switch."""

from typing import TYPE_CHECKING

from prettyqt.qt import QtCore
import pytest

from datacook import i18n
from datacook.app.actions import OpActions
from datacook.app.mainwindow import MainWindow
from datacook.engine.ops import sources
from tests.app.conftest import drain


if TYPE_CHECKING:
    from collections.abc import Iterator

    from datacook.app.controllers import AppController
    from datacook.app.controllers.app import Message


@pytest.fixture
def window(app: AppController, qtbot) -> Iterator[MainWindow]:
    win = MainWindow(app, modules=("datacook.app.docks.params", "datacook.app.actions"))
    qtbot.addWidget(win)
    yield win
    win.close()
    win.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    i18n.set_language(None)


@pytest.fixture
def actions(window: MainWindow) -> OpActions:
    found = window.findChild(OpActions)
    assert found is not None
    return found


def test_palette_lists_every_op(app: AppController, actions: OpActions) -> None:
    listed = [a.data() for a in actions.palette.get_actions()]
    assert sorted(listed) == sorted(app.session.registry.ids())
    for action in actions.palette.get_actions():
        op = app.session.registry.get(action.data())
        assert action.text() == str(op.title)


def test_steps_menu_groups_by_category(
    app: AppController, window: MainWindow, actions: OpActions
) -> None:
    menu = window.menu("steps")
    titles = [a.text() for a in menu.actions()]
    assert titles[:3] == ["Command palette…", "Edit step…", "Cancel preview"]
    in_menus = {a.data() for sub in actions.category_menus.values() for a in sub.actions()}
    assert in_menus == set(app.session.registry.ids())
    # categories in `engine.categories` order: Import first
    first_sub = next(a.menu() for a in menu.actions() if a.menu() is not None)
    assert first_sub is actions.category_menus["source"]


def test_palette_action_starts_preview(app: AppController, actions: OpActions) -> None:
    root = app.commands.add_node(sources.InlineData.record(data={"a": [1]}))
    drain(app)
    app.state.current = root
    action = next(a for a in actions.palette.get_actions() if a.data() == "sort_rows")
    action.trigger()
    spec = app.state.preview
    assert spec is not None
    assert (spec.mode, spec.op_id, spec.inputs) == ("add", "sort_rows", (root,))
    # readers start a root (no inputs)
    actions.actions["read_csv"].trigger()
    assert app.state.preview is not None
    assert app.state.preview.inputs == ()


def test_step_needs_a_current_node(app: AppController, actions: OpActions) -> None:
    messages: list[Message] = []
    app.message_posted.connect(messages.append)
    assert not actions.start("head")
    assert app.state.preview is None
    assert messages[-1].level == "warning"


def test_merge_asks_for_second_input(app: AppController, actions: OpActions) -> None:
    left = app.commands.add_node(sources.InlineData.record(data={"a": [1]}))
    right = app.commands.add_node(sources.InlineData.record(data={"b": [1]}))
    drain(app)
    app.state.current = left
    asked: list[list[str]] = []

    def choose(op_id: str, candidates) -> str | None:
        asked.append([n.id for n in candidates])
        return right

    actions.choose_input = choose
    assert actions.start("merge")
    assert asked == [[right]]
    assert app.state.preview is not None
    assert app.state.preview.inputs == (left, right)
    actions.choose_input = lambda _op, _c: None  # cancelled
    app.preview.cancel()
    assert not actions.start("merge")
    assert app.state.preview is None


def test_edit_action_opens_edit_preview(app: AppController, actions: OpActions) -> None:
    assert not actions.edit_action.isEnabled()
    root = app.commands.add_node(sources.InlineData.record(data={"a": [1]}))
    drain(app)
    app.state.current = root
    assert actions.edit_action.isEnabled()
    actions.edit_action.trigger()
    spec = app.state.preview
    assert spec is not None
    assert (spec.mode, spec.target) == ("edit", root)


def test_language_change_retexts_actions(app: AppController, actions: OpActions) -> None:
    i18n.set_language("de")
    app.state.language = "de"
    texts = {a.data(): a.text() for a in actions.palette.get_actions()}
    assert texts["sort_rows"] == str(app.session.registry.get("sort_rows").title)
    assert actions.palette_action.text() == str(i18n._("Command palette…"))
    i18n.set_language(None)
    app.state.language = None
    assert actions.actions["sort_rows"].text() == "Sort rows"
