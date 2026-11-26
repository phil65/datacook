"""Data view: slot states, display-only sort (permutation), "Add as sort step", display switch."""

from typing import TYPE_CHECKING

import pandas as pd
from prettyqt.qt import QtCore
import pytest

from datacook.app.docks.dataview import DataView
from datacook.app.slots import SlotState
from datacook.app.state import SortSpec
from datacook.engine import OpError
from datacook.engine.ops import rows, sources
from tests.app.conftest import check_invariant, drain, frame


if TYPE_CHECKING:
    from datacook.app.controllers import AppController
    from datacook.app.testing import FakeSession


@pytest.fixture
def view(qtbot, app: AppController) -> DataView:
    widget = DataView(app)
    widget.resize(800, 600)
    qtbot.addWidget(widget)
    return widget


def _chain(app: AppController) -> tuple[str, str]:
    root = app.commands.add_node(sources.InlineData.record(data={"a": [1]}), name="data")
    a = app.commands.add_node(rows.Head.record(n=2), [root], name="a")
    drain(app)
    return root, a


def _overlay(view: DataView) -> str | None:
    overlay = view.page.overlay
    return overlay.title.text() if overlay.isVisibleTo(view) else None


def test_slot_states_drive_the_overlay(
    view: DataView, app: AppController, fake: FakeSession
) -> None:
    view.show()
    assert _overlay(view) == "No step selected"
    root, a = _chain(app)
    app.state.current = a
    assert _overlay(view) == "Computing…"
    fake.complete(fake.pending(a)[0], frame(2))
    drain(app)
    assert app.nodes.slot.state == SlotState.READY
    assert _overlay(view) is None
    assert view.viewer.holder is app.nodes.slot.holder  # bound once, never replaced
    # invalidated -> recomputing, frame dropped
    app.commands.edit_params(a, rows.Head.record(n=1))
    drain(app)
    assert _overlay(view) == "Recomputing…"
    assert view.viewer.df is None
    fake.complete(fake.pending(a)[0], frame(1))
    drain(app)
    assert _overlay(view) is None
    # explicit drop -> "Not in memory" + Recompute
    fake.drop(a)
    drain(app)
    assert _overlay(view) == "Not in memory"
    recompute = view.page.overlay.button("Recompute")
    assert recompute is not None
    recompute.click()
    assert app.nodes.slot.state == SlotState.LOADING
    fake.fail(fake.pending(a)[0], OpError("boom"), failing=root)
    drain(app)
    assert _overlay(view) == "Step data failed"
    assert "boom" in view.page.overlay.detail.text()
    go = view.page.overlay.button("Go to step")
    assert go is not None
    go.click()
    assert app.state.current == root
    check_invariant(app)


def test_display_switches_to_preview_page(view: DataView, app: AppController) -> None:
    assert view.stack.currentWidget() is view.pages["node"]
    app.state.display = "preview"
    assert view.stack.currentWidget() is view.pages["preview"]
    assert view.viewer.holder is app.preview.slot.holder
    app.state.display = "node"
    assert view.page.key == "node"


def _sorted_view(qtbot, view: DataView, app: AppController, fake: FakeSession) -> tuple[str, str]:
    root, a = _chain(app)
    fake.put(a, pd.DataFrame({"x": [3, 1, 2], "y": ["c", "a", "b"]}))
    fake.put(root, frame())
    drain(app)
    app.state.current = a
    assert app.nodes.slot.state == SlotState.READY
    return root, a


def test_header_sort_is_a_permutation_not_a_copy(
    qtbot, view: DataView, app: AppController, fake: FakeSession
) -> None:
    root, a = _sorted_view(qtbot, view, app, fake)
    cached = fake.materialize(a)
    view.viewer.sort_requested.emit(0, QtCore.Qt.SortOrder.DescendingOrder)  # header click
    assert app.state.sort == SortSpec("x", descending=True)
    qtbot.waitUntil(lambda: view.page.model.row_order is not None, timeout=2000)
    assert not view.is_sorting()
    assert view.viewer.df is cached  # the cached frame itself: no sorted copy
    assert list(view.page.model.row_order) == [0, 2, 1]
    model = view.page.model
    assert [model.data(model.index(r, 0)) for r in range(3)] == ["3", "2", "1"]
    assert "Sorted by x" in view.banner.text()
    check_invariant(app)
    # selecting another node resets the display sort
    app.state.current = root
    assert app.state.sort is None
    assert view.page.model.row_order is None
    app.state.current = a
    assert view.page.model.row_order is None
    assert [model.data(model.index(r, 0)) for r in range(3)] == ["3", "1", "2"]
    check_invariant(app)


def test_sort_reapplied_after_recompute_of_same_node(
    qtbot, view: DataView, app: AppController, fake: FakeSession
) -> None:
    _root, a = _sorted_view(qtbot, view, app, fake)
    app.state.sort = SortSpec("x")
    qtbot.waitUntil(lambda: view.page.model.row_order is not None, timeout=2000)
    fake.drop(a)
    drain(app)
    app.nodes.recompute()
    fake.complete(fake.pending(a)[0], pd.DataFrame({"x": [2, 1]}))
    drain(app)
    qtbot.waitUntil(lambda: view.page.model.row_order is not None, timeout=2000)
    assert list(view.page.model.row_order) == [1, 0]


def test_add_as_sort_step_creates_a_node(
    qtbot, view: DataView, app: AppController, fake: FakeSession
) -> None:
    _root, a = _sorted_view(qtbot, view, app, fake)
    app.state.sort = SortSpec("x", descending=True)
    menu = view.header_menu("x", "node")
    action = next(act for act in menu.actions() if act.objectName() == "add-sort-step")
    assert action.isEnabled()
    action.trigger()
    drain(app)
    new = app.state.current
    assert new is not None
    assert new != a
    node = app.session.get(new)
    assert node.parents == (a,)
    assert node.record == rows.SortRows.record(by=["x"], ascending=False)
    assert app.state.sort is None
    app.commands.undo()
    drain(app)
    assert new not in app.session
    assert app.state.current == a
    check_invariant(app)


def test_prefetch_runs_on_view_pool(
    qtbot, view: DataView, app: AppController, fake: FakeSession
) -> None:
    _root, a = _chain(app)
    fake.put(a, pd.DataFrame({"x": range(2000)}))
    drain(app)
    app.state.current = a
    view.show()
    model = view.page.model
    model.cache.clear()
    view.page.prefetch()
    qtbot.waitUntil(lambda: len(model.cache) > 0, timeout=2000)
