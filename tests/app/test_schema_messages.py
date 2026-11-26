"""WP D docks: schema / column profile, messages / log, and the language switch."""

import json
import logging
import threading
from typing import TYPE_CHECKING

import pandas as pd
from prettyqt.custom_widgets.pydanticform import PydanticForm
from prettyqt.qt import QtCore, QtWidgets
from pydantic import BaseModel, Field
import pytest

from datacook import i18n
from datacook.app import application
from datacook.app.docks import messages, schema
from datacook.app.mainwindow import MainWindow
from datacook.engine import OpError
from datacook.engine.ops import rows, sources
from tests.app.conftest import check_invariant, drain


if TYPE_CHECKING:
    from collections.abc import Iterator

    from datacook.app.controllers import AppController
    from datacook.app.testing import FakeSession


MODULES = ("datacook.app.docks.schema", "datacook.app.docks.messages")


def _frame() -> pd.DataFrame:
    return pd.DataFrame({
        "a": [1, 2, 2, 3],
        "b": pd.Categorical(["x", "y", "x", "x"]),
    })


def _root(app: AppController, fake: FakeSession, frame: pd.DataFrame | None = None) -> str:
    root = app.commands.add_node(sources.InlineData.record(data={"a": [1]}))
    fake.put(root, _frame() if frame is None else frame)
    drain(app)
    return root


def _wait_drained(qtbot, app: AppController, condition) -> None:
    def check() -> bool:
        drain(app)
        return bool(condition())

    qtbot.waitUntil(check, timeout=3000)


@pytest.fixture
def schema_widget(qtbot, app: AppController) -> schema.SchemaWidget:
    widget = schema.SchemaWidget(app)
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def messages_widget(qtbot, app: AppController) -> Iterator[messages.MessagesWidget]:
    widget = messages.MessagesWidget(app)
    qtbot.addWidget(widget)
    widget.show()
    yield widget
    widget.detach_log_handler()


# --- schema / profile --------------------------------------------------------------------


def test_schema_follows_selection(qtbot, app, fake, schema_widget) -> None:
    assert schema_widget.table.model().rowCount() == 0
    root = _root(app, fake)
    app.state.current = root
    model = schema_widget.table.model()
    assert model.rowCount() == 2
    assert [model.index(r, 0).data() for r in range(2)] == ["a", "b"]
    # column selection in the table -> state.column -> stats from the view pool
    schema_widget.table.selectRow(1)
    assert app.state.column == "b"
    _wait_drained(qtbot, app, lambda: schema_widget.profile.value_labels["Rows"].text())
    assert schema_widget.profile.value_labels["Rows"].text() == "4"
    assert schema_widget.profile.value_labels["Unique"].text() == "2"
    # categorical column: categories listed
    assert schema_widget.categories is not None
    assert schema_widget.categories.rowCount() == 2
    assert not schema_widget.category_table.isHidden()
    # state.column -> table selection
    app.state.column = "a"
    assert schema_widget.table.currentIndex().row() == 0
    _wait_drained(qtbot, app, lambda: schema_widget.profile.value_labels["Mean"].text())
    assert schema_widget.profile.value_labels["Mean"].text() == "2"
    assert schema_widget.category_table.isHidden()
    # deselecting the node clears the schema and the profile
    app.state.current = None
    assert schema_widget.table.model().rowCount() == 0
    assert schema_widget.profile.value_labels["Rows"].text() == ""
    check_invariant(app)


def test_profile_hint_without_selected_column(qtbot, app, fake, schema_widget) -> None:
    assert schema_widget.hint.isHidden()  # nothing displayed: no hint either
    root = _root(app, fake)
    app.state.current = root
    assert not schema_widget.hint.isHidden()
    assert schema_widget.profile.isHidden()
    assert "column" in schema_widget.hint.text()
    app.state.column = "a"
    assert schema_widget.hint.isHidden()
    assert not schema_widget.profile.isHidden()


def test_schema_follows_display_slot(qtbot, app, fake, schema_widget) -> None:
    root = _root(app, fake)
    app.state.current = root
    app.state.column = "a"
    _wait_drained(qtbot, app, lambda: schema_widget.profile.value_labels["Rows"].text())
    app.preview.slot.show(None, pd.DataFrame({"a": [5.0, 6.0], "c": ["u", "v"]}))
    app.state.display = "preview"
    model = schema_widget.table.model()
    assert model is schema_widget.models["preview"]
    assert [model.index(r, 0).data() for r in range(model.rowCount())] == ["a", "c"]
    _wait_drained(qtbot, app, lambda: schema_widget.profile.value_labels["Rows"].text() == "2")
    app.state.display = "node"
    assert schema_widget.table.model() is schema_widget.models["node"]
    _wait_drained(qtbot, app, lambda: schema_widget.profile.value_labels["Rows"].text() == "4")
    app.preview.slot.clear()


def test_stale_profile_results_are_dropped(qtbot, app, fake, schema_widget, monkeypatch) -> None:
    release = threading.Event()
    real = schema._describe

    def describe(source, position):
        if source.columns[position].name == "a":
            release.wait(5)
        return real(source, position)

    monkeypatch.setattr(schema, "_describe", describe)
    shown: list[str] = []
    original = schema_widget.profile.set_stats
    monkeypatch.setattr(
        schema_widget.profile,
        "set_stats",
        lambda info, stats: (shown.append(info.name), original(info, stats)),
    )
    root = _root(app, fake)
    app.state.current = root
    app.state.column = "a"  # blocked in the worker
    app.state.column = "b"  # supersedes it
    _wait_drained(qtbot, app, lambda: shown)
    release.set()
    # the late result for "a" arrives but is not shown
    qtbot.wait(100)
    drain(app)
    assert shown == ["b"]
    assert schema_widget.profile.value_labels["Unique"].text() == "2"

    # the frame goes away while a profile job runs: its result is dropped too
    release.clear()
    app.state.column = "a"
    app.state.current = None
    release.set()
    qtbot.wait(100)
    drain(app)
    assert shown == ["b"]
    assert schema_widget.profile.value_labels["Rows"].text() == ""


# --- messages ----------------------------------------------------------------------------


def _texts(widget: messages.MessagesWidget) -> list[str]:
    proxy = widget.proxy
    return [proxy.index(r, 2).data() for r in range(proxy.rowCount())]


def test_messages_show_notify_errors_and_logs(qtbot, app, fake, messages_widget) -> None:
    root = _root(app, fake)
    child = app.commands.add_node(rows.Head.record(n=1), [root], name="first rows")
    drain(app)
    app.notify("hello", "warning", node_id=root)
    # a failing step
    app.state.current = child
    (req,) = fake.pending(child)
    fake.fail(req, OpError("bad op"), failing=child)
    drain(app)
    # log records of datacook loggers, also from a worker thread
    logging.getLogger("datacook.engine.test").warning("from the engine")
    thread = threading.Thread(
        target=lambda: logging.getLogger("datacook.app.x").error("from a worker")
    )
    thread.start()
    thread.join()
    logging.getLogger("otherlib").warning("not ours")
    _wait_drained(qtbot, app, lambda: "from a worker" in _texts(messages_widget))
    texts = _texts(messages_widget)
    assert texts[0] == "hello"
    assert texts[1] == "first rows: bad op"
    assert texts[2:] == ["from the engine", "from a worker"]
    entries = messages_widget.model.entries
    assert [e.level for e in entries] == ["warning", "error", "warning", "error"]
    assert entries[1].node_id == child
    # level filter
    messages_widget.level_combo.setCurrentIndex(list(messages.LEVELS).index("error"))
    assert _texts(messages_widget) == ["first rows: bad op", "from a worker"]
    messages_widget.level_combo.setCurrentIndex(list(messages.LEVELS).index("info"))
    assert len(_texts(messages_widget)) == 4
    messages_widget.clear_button.click()
    assert _texts(messages_widget) == []


def test_click_on_message_selects_node(qtbot, app, fake, messages_widget) -> None:
    root = _root(app, fake)
    app.notify("look here", node_id=root)
    app.notify("no node")
    view = messages_widget.view
    rect = view.visualRect(messages_widget.proxy.index(1, 2))
    qtbot.mouseClick(view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=rect.center())
    assert app.state.current is None
    rect = view.visualRect(messages_widget.proxy.index(0, 2))
    qtbot.mouseClick(view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=rect.center())
    assert app.state.current == root
    # a removed step cannot be selected
    app.state.current = None
    app.commands.remove_subtree(root)
    drain(app)
    qtbot.mouseClick(view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=rect.center())
    assert app.state.current is None


def test_log_handler_detached_with_widget(qtbot, app) -> None:
    logger = logging.getLogger(messages.LOGGER_NAME)
    widget = messages.MessagesWidget(app)
    assert widget.log_handler in logger.handlers
    handler = widget.log_handler
    widget.deleteLater()
    qtbot.waitUntil(lambda: handler not in logger.handlers, timeout=2000)


def test_message_list_is_bounded(app) -> None:
    model = messages.MessageModel(max_entries=3)
    for i in range(5):
        model.append(messages.Entry(str(i)))
    assert [e.text for e in model.entries] == ["2", "3", "4"]


# --- language switch ---------------------------------------------------------------------


class _Params(BaseModel):
    rows: int = Field(5, title=i18n.N_("Rows"))


def _language_action(window: MainWindow, code: str | None):
    menu = window.findChild(QtWidgets.QMenu, "menu-language")
    assert menu is not None
    (action,) = [a for a in menu.actions() if not a.isSeparator() and a.data() == code]
    return action


def test_language_switch_keeps_state(qtbot, app, fake, tmp_path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("datacook.app.settings.default_path", lambda: settings_file)
    window = MainWindow(app, modules=MODULES)
    qtbot.addWidget(window)
    form = PydanticForm(_Params, translate=i18n.translate, debounce_ms=0, parent=window)
    form.set_value({"rows": 7})
    root = _root(app, fake)
    app.state.current = root
    app.state.column = "a"
    widget = window.widgets["schema"]
    assert isinstance(widget, schema.SchemaWidget)
    _wait_drained(qtbot, app, lambda: widget.profile.value_labels["Rows"].text())
    app.notify("kept")
    assert window.docks["schema"].windowTitle() == "Columns"
    assert widget.table.model().headerData(1, QtCore.Qt.Orientation.Horizontal) == "Type"
    assert widget.profile.field_labels["Rows"].text() == "Rows:"
    assert form.layout().labelForField(form.get_editor("rows").parentWidget()) is not None
    try:
        _language_action(window, "de").trigger()
        assert app.state.language == "de"
        assert json.loads(settings_file.read_text())["language"] == "de"
        assert window.docks["schema"].windowTitle() == "Spalten"
        assert window.menu("view").title() == "&Ansicht"
        assert widget.table.model().headerData(1, QtCore.Qt.Orientation.Horizontal) == "Typ"
        assert widget.profile.field_labels["Rows"].text() == "Zeilen:"
        labels = [w.text() for w in form.findChildren(QtWidgets.QLabel)]
        assert "Zeilen" in labels or "Zeilen:" in labels
        # nothing lost
        assert app.state.current == root
        assert app.state.column == "a"
        assert widget.profile.value_labels["Rows"].text() == "4"
        assert form.get_value() == _Params(rows=7)
        assert window.widgets["messages"].model.entries[-1].text == "kept"

        _language_action(window, "en").trigger()
        assert json.loads(settings_file.read_text())["language"] == "en"
        assert window.docks["schema"].windowTitle() == "Columns"
        assert widget.profile.field_labels["Rows"].text() == "Rows:"
        assert widget.table.model().headerData(1, QtCore.Qt.Orientation.Horizontal) == "Type"
        labels = [w.text() for w in form.findChildren(QtWidgets.QLabel)]
        assert "Rows" in labels or "Rows:" in labels
        assert form.get_value() == _Params(rows=7)
        assert app.state.current == root
    finally:
        application.set_language(app, None)
        window.close()


def test_system_default_language_is_saved_as_none(qtbot, app, tmp_path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("datacook.app.settings.default_path", lambda: settings_file)
    monkeypatch.setattr(application, "system_language", lambda: "de")
    window = MainWindow(app, modules=MODULES)
    qtbot.addWidget(window)
    try:
        _language_action(window, None).trigger()
        assert json.loads(settings_file.read_text())["language"] is None
        assert app.state.language == "de"
        assert window.docks["messages"].windowTitle() == str(i18n._("Messages"))
    finally:
        application.set_language(app, None)
    assert app.state.language is None


def test_qt_translator_follows_language(app) -> None:
    try:
        application.set_language(app, "de")
        assert application._qt_translator is not None
        assert application._qt_translator.language().startswith("de")
    finally:
        application.set_language(app, None)
    assert application._qt_translator is None
