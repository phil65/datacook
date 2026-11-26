"""Code pane (span follows selection, error markers) and the memory indicator."""

from typing import TYPE_CHECKING

import pytest

from datacook.app.docks import code
from datacook.app.widgets import memoryindicator
from datacook.app.widgets.memoryindicator import GB, MemoryIndicator
from datacook.engine import MemoryStats, OpError, Session
from datacook.engine.ops import rows, sources
from tests.app.conftest import check_invariant, drain, frame


if TYPE_CHECKING:
    from datacook.app.controllers import AppController
    from datacook.app.testing import FakeSession


def _chain(app: AppController) -> tuple[str, str, str]:
    root = app.commands.add_node(sources.InlineData.record(data={"a": [1]}), name="data")
    a = app.commands.add_node(rows.Head.record(n=2), [root], name="a")
    b = app.commands.add_node(rows.Head.record(n=1), [a], name="b")
    drain(app)
    return root, a, b


def _span_lines(controller: code.CodeController) -> list[int]:
    return sorted(
        s.cursor.blockNumber() + 1 for s in controller.editor.extraSelections() if code._is_span(s)
    )


def test_code_span_follows_selection(qtbot, app: AppController, fake: FakeSession) -> None:
    pane = code.CodePane(app)
    qtbot.addWidget(pane)
    controller = pane.controller
    root, a, b = _chain(app)
    qtbot.waitUntil(lambda: "# b" in pane.editor.toPlainText(), timeout=2000)
    assert pane.editor.isReadOnly()
    assert controller.spans[a] == (2, 2)
    assert _span_lines(controller) == []
    app.state.current = a
    assert _span_lines(controller) == [2]
    app.state.current = b
    assert _span_lines(controller) == [3]
    app.commands.rename(b, "last")
    drain(app)
    qtbot.waitUntil(lambda: "# last" in pane.editor.toPlainText(), timeout=2000)
    assert _span_lines(controller) == [3]
    fake.fail(fake.pending(b)[0], OpError("head: boom"), failing=a)
    drain(app)
    markers = pane.editor.get_line_markers()
    assert [m.line for m in markers] == [2]
    assert "boom" in markers[0].message
    assert _span_lines(controller) == [3]  # the highlight survives the marker update
    app.commands.remove_subtree(root)
    drain(app)
    qtbot.waitUntil(lambda: pane.editor.toPlainText() == "", timeout=2000)
    check_invariant(app)


def test_code_pane_real_engine_spans(qtbot) -> None:
    from datacook.app.controllers import AppController
    from datacook.app.settings import AppSettings

    app = AppController(Session(), AppSettings(selection_debounce_ms=0))
    try:
        pane = code.CodePane(app)
        qtbot.addWidget(pane)
        root = app.commands.add_node(sources.InlineData.record(data={"a": [1, 2]}), name="data")
        a = app.commands.add_node(rows.Head.record(n=1), [root])
        qtbot.waitUntil(lambda: ".head(1)" in pane.editor.toPlainText(), timeout=2000)
        app.state.current = a
        first, last = pane.controller.spans[a]
        lines = pane.editor.toPlainText().splitlines()
        assert lines[first - 1].startswith("# ")
        assert ".head(1)" in lines[last - 1]
        assert _span_lines(pane.controller) == list(range(first, last + 1))
        qtbot.waitUntil(lambda: app.nodes.slot.state == "ready", timeout=2000)
    finally:
        app.close()


@pytest.fixture
def indicator(qtbot, app: AppController, monkeypatch) -> MemoryIndicator:
    monkeypatch.setattr(memoryindicator, "process_rss", lambda: int(2.1 * GB))
    widget = MemoryIndicator(app)
    qtbot.addWidget(widget)
    return widget


def test_memory_indicator_values(
    app: AppController, fake: FakeSession, indicator, monkeypatch
) -> None:
    monkeypatch.setattr(fake, "memory", lambda: MemoryStats(int(1.2 * GB), 4 * GB, 2, 1))
    indicator.refresh()
    assert indicator.text() == "Cache 1.2/4.0 GB · RSS 2.1 GB"
    assert not indicator.over_budget
    monkeypatch.setattr(fake, "memory", lambda: MemoryStats(5 * GB, 4 * GB, 2, 1))
    app.bridge.memory_changed.emit()
    assert indicator.text() == "Cache 5.0/4.0 GB · RSS 2.1 GB"
    assert indicator.over_budget
    assert "2 steps in memory" in indicator.toolTip()


def test_memory_indicator_menu_and_free(app: AppController, fake: FakeSession, indicator) -> None:
    root, a, b = _chain(app)
    for nid in (root, a, b):
        fake.put(nid, frame(5))
    drain(app)
    app.state.current = a  # pins a + root
    entries = indicator.cached_entries()
    assert {e[0] for e in entries} == {root, a, b}
    assert all(e[2] is not None for e in entries)
    indicator._fill_menu()
    texts = [act.text() for act in indicator.menu_.actions()]
    assert any(t.startswith("a ") and "[pinned]" in t for t in texts)
    messages: list[str] = []
    app.message_posted.connect(lambda m: messages.append(m.text))
    free = next(act for act in indicator.menu_.actions() if act.objectName() == "free-memory")
    free.trigger()
    drain(app)
    assert set(fake.cached_ids()) == {root, a}
    assert messages == ["Freed 1 cached steps"]
    check_invariant(app)
    # choosing a cached step selects it
    indicator._fill_menu()
    pick = next(act for act in indicator.menu_.actions() if act.text().startswith("data"))
    pick.trigger()
    assert app.state.current == root


def test_main_window_wires_the_wpb_docks(qtbot, app: AppController, fake: FakeSession) -> None:
    from datacook.app.docks.dataview import DataView
    from datacook.app.docks.nodetree import NodeTreeWidget
    from datacook.app.mainwindow import MainWindow

    window = MainWindow(app)
    qtbot.addWidget(window)
    assert isinstance(window.centralWidget(), DataView)
    assert isinstance(window.widgets["nodetree"], NodeTreeWidget)
    assert isinstance(window.widgets["code"], code.CodePane)
    assert isinstance(window.widgets["memory"], MemoryIndicator)
    steps = [a.text() for a in window.menu("steps").actions()]
    assert "Delete step" in steps
    root, a, _b = _chain(app)
    window.widgets["nodetree"].view.setCurrentIndex(window.widgets["nodetree"].model.index_of(a))
    assert app.state.current == a
    fake.complete(fake.pending(a)[0], frame(2))
    drain(app)
    assert window.centralWidget().viewer.df is fake.materialize(a)
    check_invariant(app)
    window.close()
    assert fake.pin_counts() == {}
    assert root in app.session
