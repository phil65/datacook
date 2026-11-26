"""Offscreen smoke test of the whole app: the real MainWindow with every UI module.

Load a CSV through the reader dialog -> filter, rename, groupby via the op actions and the
params form -> branch -> preview edit -> commit -> undo / redo -> display sort -> export
the script, run it in a subprocess and compare its frame -> save / open round trip.
Plus a (slow, opt-in) memory scenario on a few million rows.
"""

import os
import pickle
import subprocess
import sys
import textwrap
import time
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from prettyqt.qt import QtCore, QtGui
import pytest

from datacook import allocator
from datacook.app.actions import OpActions
from datacook.app.controllers import AppController
from datacook.app.controllers.project import ProjectController
from datacook.app.docks.dataview import DataView
from datacook.app.docks.params import ParamsPanel
from datacook.app.mainwindow import MainWindow
from datacook.app.settings import AppSettings
from datacook.app.slots import SlotState
from datacook.app.state import SortSpec
from datacook.app.widgets.readerdialog import ReaderDialog
from datacook.engine import parser
from tests.app.conftest import check_invariant


if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    import pathlib

    from prettyqt.qt import QtWidgets


TIMEOUT = 10_000


@pytest.fixture
def window(qapp, qtbot) -> Iterator[MainWindow]:
    settings = AppSettings(selection_debounce_ms=0, preview_debounce_ms=0, preview_rows=50)
    app = AppController(settings=settings)
    win = MainWindow(app)
    qtbot.addWidget(win)
    win.resize(1400, 900)
    win.show()
    yield win
    win.close()
    assert app.pins.pinned_ids() == frozenset()


def _csv(path: pathlib.Path) -> pathlib.Path:
    rng = np.random.default_rng(0)
    n = 500
    pd.DataFrame({
        "city": rng.choice(["Berlin", "Hamburg", "Munich", "Cologne"], n),
        "year": rng.integers(2020, 2025, n),
        "sales": rng.normal(100, 30, n).round(2),
        "qty": rng.integers(1, 20, n),
    }).to_csv(path, index=False)
    return path


class Driver:
    """Drives the window like a user: actions, the params form, Apply."""

    def __init__(self, window: MainWindow, qtbot: Any):
        self.window = window
        self.app = window.app
        self.qtbot = qtbot
        project = window.project
        assert isinstance(project, ProjectController)
        self.project = project
        ops = window.findChild(OpActions, "op-actions")
        assert ops is not None
        self.ops = ops
        params = window.widgets["params"]
        assert isinstance(params, ParamsPanel)
        self.params = params
        view = window.widgets["dataview"]
        assert isinstance(view, DataView)
        self.view = view

    def wait(self, condition: Callable[[], object]) -> None:
        self.qtbot.waitUntil(lambda: bool(condition()), timeout=TIMEOUT)

    def wait_current_ready(self) -> pd.DataFrame:
        self.wait(lambda: self.app.nodes.slot.state == SlotState.READY)
        df = self.app.nodes.slot.holder.df
        assert df is not None
        return df

    def wait_preview_ready(self) -> pd.DataFrame:
        self.wait(lambda: self.app.preview.slot.state == SlotState.READY)
        df = self.app.preview.slot.holder.df
        assert df is not None
        return df

    def action(self, name: str) -> QtGui.QAction:
        action = self.window.findChild(QtGui.QAction, name)
        assert action is not None, name
        return action

    def add_step(self, op_id: str, values: dict[str, Any]) -> str:
        """Steps menu action -> fill the form -> wait for the preview -> Apply."""
        self.action(f"op-{op_id}").trigger()
        assert self.app.state.preview is not None
        assert self.params.form is not None
        self.params.form.set_value(values)
        self.wait_preview_ready()
        node_id = self.params.apply()
        assert node_id is not None
        assert self.app.state.current == node_id
        self.wait_current_ready()
        return node_id


def test_smoke_whole_app(window: MainWindow, qtbot, tmp_path: pathlib.Path) -> None:
    d = Driver(window, qtbot)
    app = d.app
    csv = _csv(tmp_path / "sales.csv")
    source = pd.read_csv(csv)

    # 1. load the CSV through the reader dialog (accepted once its preview is shown)
    def accept(dialog: QtWidgets.QDialog) -> bool:
        assert isinstance(dialog, ReaderDialog)
        d.wait(lambda: dialog.viewer.holder.df is not None)
        return True

    d.project.exec_dialog = accept
    root = d.project.open_data(csv)
    assert root is not None
    assert len(d.wait_current_ready()) == len(source)
    assert window.windowTitle() == "Untitled* - DataCook"

    # 2. three ops: filter, rename, groupby
    flt = d.add_step("filter_rows", {"expr": "sales > 100"})
    assert len(app.nodes.slot.holder.df) == (source.sales > 100).sum()
    ren = d.add_step("rename_columns", {"columns": {"qty": "quantity"}})
    assert "quantity" in app.nodes.slot.holder.df.columns
    grp = d.add_step(
        "groupby_aggregate",
        {"by": ["city"], "aggregations": [{"column": "quantity", "func": "sum"}]},
    )
    grouped = app.nodes.slot.holder.df
    assert list(grouped.columns) == ["city", "quantity_sum"]
    assert len(grouped) == 4
    check_invariant(app)

    # 3. branch: a sort step on the filter step (which already has a child)
    app.state.current = flt
    d.wait_current_ready()
    branch = d.add_step("sort_rows", {"by": ["sales"], "ascending": False})
    assert [n.id for n in app.session.children(flt)] == [ren, branch]
    top = app.nodes.slot.holder.df.sales.iloc[0]
    assert top == source.sales.max()

    # 4. preview edit of the rename step, then commit (downstream groupby follows)
    app.state.current = ren
    d.wait_current_ready()
    d.action("action-edit-step").trigger()
    assert d.params.form is not None
    d.params.form.set_value({"columns": {"qty": "units"}})
    d.wait(
        lambda: (
            app.preview.slot.state == SlotState.READY
            and "units" in app.preview.slot.holder.df.columns
        )
    )
    assert app.state.display == "preview"
    assert d.params.apply() == ren
    d.wait(
        lambda: (
            app.nodes.slot.state == SlotState.READY and "units" in app.nodes.slot.holder.df.columns
        )
    )
    app.state.current = grp
    d.wait(lambda: app.nodes.slot.state == SlotState.ERROR)  # 'quantity' is gone now

    # 5. undo / redo of the edit
    window.undo_action.trigger()
    d.wait_current_ready()
    assert list(app.nodes.slot.holder.df.columns) == ["city", "quantity_sum"]
    window.redo_action.trigger()
    d.wait(lambda: app.nodes.slot.state == SlotState.ERROR)
    window.undo_action.trigger()
    grouped = d.wait_current_ready()

    # 6. display-only sort (view state, no new step, no frame copy)
    n_nodes = len(app.session.nodes())
    d.view.viewer.sort_requested.emit(1, QtCore.Qt.SortOrder.DescendingOrder)  # header click
    assert app.state.sort == SortSpec("quantity_sum", descending=True)
    d.wait(lambda: not d.view.is_sorting() and d.view.viewer.holder.row_order is not None)
    model = d.view.page.model
    shown = [model.data(model.index(r, 1)) for r in range(model.rowCount())]
    expected = grouped.quantity_sum.sort_values(ascending=False)
    assert shown == [str(v) for v in expected]
    assert d.view.viewer.df is grouped  # the cached frame, not a sorted copy
    assert len(app.session.nodes()) == n_nodes
    check_invariant(app)

    # 7. export the script, run it in a subprocess, compare the frame
    script = tmp_path / "pipeline.py"
    assert d.project.export_script(script)
    last = parser.parse(script.read_text(), app.session.registry).steps[-1].output
    out = tmp_path / "result.pkl"
    runner = textwrap.dedent(f"""
        import pickle, runpy
        ns = runpy.run_path({str(script)!r})
        with open({str(out)!r}, "wb") as f:
            pickle.dump(ns[{last!r}], f)
    """)
    env = {**os.environ, "PYTHONPATH": ""}
    subprocess.run([sys.executable, "-c", runner], check=True, env=env, timeout=120)
    with out.open("rb") as f:
        result = pickle.load(f)
    pd.testing.assert_frame_equal(result, app.session.materialize(grp))

    # 8. save / open round trip
    project_file = tmp_path / "demo.datacook"
    assert d.project.save_as(project_file)
    assert window.windowTitle() == "demo.datacook - DataCook"
    before = [(n.id, n.record, n.parents, n.name) for n in app.session.nodes()]
    assert d.project.new()
    assert not app.session.nodes()
    assert d.project.open(project_file)
    after = [(n.id, n.record, n.parents, n.name) for n in app.session.nodes()]
    assert after == before
    app.state.current = grp
    pd.testing.assert_frame_equal(d.wait_current_ready(), result)
    assert not d.project.dirty
    check_invariant(app)


def _settle(app: AppController, qtbot: Any) -> None:
    """Wait until no job is live and Arrow's allocated bytes stop changing.

    Superseded jobs (a cancelled column scan, a dropped preview) still run to the end on
    their worker and hold their frames until then.
    """
    import pyarrow as pa

    qtbot.waitUntil(lambda: len(app.jobs) == 0, timeout=60_000)
    last, stable = -1, 0
    for _ in range(100):
        now = pa.total_allocated_bytes()
        stable = stable + 1 if now == last else 0
        if stable == 3:
            return
        last = now
        qtbot.wait(100)


@pytest.mark.slow
@pytest.mark.skipif(
    not os.environ.get("DATACOOK_MEMORY_SCENARIO"),
    reason="slow memory scenario: set DATACOOK_MEMORY_SCENARIO=1",
)
def test_memory_scenario_millions_of_rows(window: MainWindow, qtbot, tmp_path) -> None:
    """Few-million-row frame through the app; prints RSS / cache numbers per stage.

    `DATACOOK_MEMORY_SCENARIO=1 ARROW_DEFAULT_MEMORY_POOL=system uv run pytest -s -k memory`
    (`DATACOOK_MEMORY_ROWS`, default 3M). Allocators as in the app (`allocator.configure`;
    the env var because pytest imports pyarrow first). RSS is measured once background jobs
    are done, after gc + `allocator.release()`.
    """
    import gc

    import psutil

    allocator.configure()
    rows = int(os.environ.get("DATACOOK_MEMORY_ROWS", "3000000"))
    d = Driver(window, qtbot)
    app = d.app
    proc = psutil.Process()
    rng = np.random.default_rng(0)
    path = tmp_path / "big.parquet"
    pd.DataFrame({
        "id": np.arange(rows),
        "group": pd.Categorical(rng.choice([f"g{i}" for i in range(50)], rows)),
        "label": rng.choice(["alpha", "beta", "gamma", "delta"], rows),
        "x": rng.normal(size=rows),
        "y": rng.normal(size=rows),
        "n": rng.integers(0, 1000, rows),
        "ts": pd.date_range("2020-01-01", periods=rows, freq="s"),
    }).to_parquet(path)
    gc.collect()
    numbers: list[tuple[str, float, float, float]] = []
    last = [time.perf_counter()]

    def record(stage: str) -> None:
        now = time.perf_counter()
        _settle(app, qtbot)
        gc.collect()
        allocator.release()
        mem = app.session.memory()
        rss = proc.memory_info().rss / 2**20
        numbers.append((stage, rss, mem.used / 2**20, now - last[0]))
        last[0] = time.perf_counter()

    record("start")
    d.project.exec_dialog = lambda dialog: (
        d.wait(lambda: dialog.viewer.holder.df is not None) or True  # ty: ignore[unresolved-attribute]
    )
    root = d.project.open_data(path)
    assert root is not None
    d.wait_current_ready()
    record("loaded")
    d.add_step("filter_rows", {"expr": "x > 0"})
    record("filter")
    d.add_step("rename_columns", {"columns": {"n": "count"}})
    record("rename")
    d.add_step("sort_rows", {"by": ["y"]})
    record("sort")
    d.add_step(
        "groupby_aggregate", {"by": ["group"], "aggregations": [{"column": "x", "func": "mean"}]}
    )
    record("groupby")
    dropped = app.free_memory()
    record(f"free memory ({len(dropped)} dropped)")
    check_invariant(app)
    print()
    for stage, rss, cache, secs in numbers:
        print(f"{stage:<28} RSS {rss:6.0f} MiB  cache {cache:6.0f} MiB  {secs:6.1f} s")
    # freed frames go back to the OS: RSS ~ start + cache (+ allocator slack); before the
    # allocator setup ~450 MiB of freed memory stayed resident here
    (_, rss_start, _, _), (_, rss_free, cache_free, _) = numbers[0], numbers[-1]
    assert rss_free - rss_start - cache_free < 200
