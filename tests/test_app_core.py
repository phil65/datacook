"""Qt-free app core: pins, event queue / coalescing, JobRunner, FakeSession, settings.

These run without Qt (also in the free-threaded 3.14t job); Qt tests are in tests/app/.
"""

import subprocess
import sys
import threading
from typing import TYPE_CHECKING, Any

import pandas as pd
import pytest

from datacook.app.eventqueue import RESET_THRESHOLD, Batch, EventQueue, Posted, coalesce
from datacook.app.jobs import JobRunner
from datacook.app.pins import PinBook
from datacook.app.settings import AppSettings
from datacook.app.testing import FakeSession
from datacook.engine import Event, EventKind
from datacook.engine.ops import rows, sources


if TYPE_CHECKING:
    import pathlib


def _frame(n: int = 3) -> pd.DataFrame:
    return pd.DataFrame({"a": list(range(n))})


def _tree(fake: FakeSession) -> tuple[str, str, str]:
    """Root -> a -> b."""
    root = fake.add(sources.InlineData.record(data={"a": [1, 2, 3]})).id
    a = fake.add(rows.Head.record(n=2), [root]).id
    b = fake.add(rows.Head.record(n=1), [a]).id
    return root, a, b


class Pump:
    """`post` for tests: a locked queue the test thread runs (stands in for the bridge)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: list[tuple[Any, tuple[Any, ...]]] = []

    def __call__(self, fn: Any, *args: Any) -> None:
        with self._lock:
            self._calls.append((fn, args))

    def run(self) -> int:
        with self._lock:
            calls, self._calls = self._calls, []
        for fn, args in calls:
            fn(*args)
        return len(calls)


def test_qt_free_core_modules() -> None:
    code = (
        "import sys\n"
        "import datacook.app, datacook.app.protocols, datacook.app.settings, datacook.app.pins\n"
        "import datacook.app.eventqueue, datacook.app.jobs, datacook.app.testing\n"
        "bad = [m for m in sys.modules if m.split('.')[0] in "
        "('PySide6', 'PyQt6', 'shiboken6', 'prettyqt', 'qtpy', 'cutepandas')]\n"
        "print(','.join(bad))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert out == ""


# --- PinBook -----------------------------------------------------------------------------


def test_pinbook_moves_and_releases_pins() -> None:
    fake = FakeSession()
    root, a, b = _tree(fake)
    pins = PinBook(fake)
    pins.set("current", (b, a))
    pins.set("preview", (a,))
    assert fake.pin_counts() == {a: 2, b: 1}
    pins.set("current", (a, root))  # a never drops to 0 in between
    assert fake.pin_counts() == {a: 2, root: 1}
    assert pins.pinned_ids() == {a, root}
    pins.release_all()
    assert fake.pin_counts() == {}
    assert pins.pinned_ids() == frozenset()


def test_pinbook_forget_removed_nodes() -> None:
    fake = FakeSession()
    root, a, b = _tree(fake)
    pins = PinBook(fake)
    pins.set("current", (b, a))
    fake.remove(a)
    pins.forget((a, b))
    assert fake.pin_counts() == {}
    pins.set("current", (root, "gone"))  # unknown ids are not pinned
    assert fake.pin_counts() == {root: 1}


# --- event queue -------------------------------------------------------------------------


def test_queue_wakes_once_per_drain() -> None:
    q = EventQueue()
    assert q.put(Posted(print)) is True
    assert q.put(Posted(print)) is False
    assert len(q.take()) == 2
    assert q.put(Posted(print)) is True


def test_queue_concurrent_producers() -> None:
    """No item is lost or duplicated with many producers and a concurrent consumer."""
    q = EventQueue()
    n_threads, n_items = 8, 2000
    taken: list[Posted] = []
    stop = threading.Event()

    def produce(t: int) -> None:
        for i in range(n_items):
            q.put(Posted(print, (t, i)))

    def consume() -> None:
        while not stop.is_set():
            taken.extend(i for i in q.take() if isinstance(i, Posted))

    consumer = threading.Thread(target=consume)
    consumer.start()
    producers = [threading.Thread(target=produce, args=(t,)) for t in range(n_threads)]
    for p in producers:
        p.start()
    for p in producers:
        p.join()
    stop.set()
    consumer.join()
    taken.extend(i for i in q.take() if isinstance(i, Posted))
    assert len(taken) == n_threads * n_items
    assert len({i.args for i in taken}) == n_threads * n_items
    # per producer, FIFO order is kept
    for t in range(n_threads):
        assert [i.args[1] for i in taken if i.args[0] == t] == list(range(n_items))


def test_coalesce_merges_runs_and_keeps_fifo() -> None:
    fake = FakeSession()
    root, a, b = _tree(fake)
    gen = fake.generations((root, a, b))
    call = Posted(print, ("done",))
    items = [
        Event(EventKind.ADDED, (root,), gen[root]),
        Event(EventKind.ADDED, (a,), gen[a]),
        Event(EventKind.MATERIALIZED, (a,), gen[a]),
        call,
        Event(EventKind.MATERIALIZED, (b,), gen[b]),
        Event(EventKind.MATERIALIZED, (root,), gen[root] - 100),  # outdated generation
        Event(EventKind.CHANGED, ("unknown",), 1),  # node does not exist
        Event(EventKind.REMOVED, ("gone",)),  # removed ids always pass
    ]
    assert coalesce(items, fake) == [
        Batch("added", (root, a)),
        Batch("materialized", (a,)),
        Batch("call", call=call),
        Batch("materialized", (b,)),
        Batch("removed", ("gone",)),
    ]


def test_coalesce_resets_on_many_events() -> None:
    fake = FakeSession()
    root, *_ = _tree(fake)
    gen = fake.generations((root,))[root]
    err = ValueError("x")
    fake.fail(fake.request(root), err)
    call = Posted(print)
    items: list[Any] = [Event(EventKind.ADDED, (root,), gen)] * (RESET_THRESHOLD + 1)
    items += [Event(EventKind.ERROR, (root,), gen, err), call]
    assert coalesce(items, fake) == [
        Batch("reset"),
        Batch("error", (root,), err),
        Batch("call", call=call),
    ]


# --- FakeSession -------------------------------------------------------------------------


def test_fake_session_materialized_before_done() -> None:
    fake = FakeSession()
    root, *_ = _tree(fake)
    order: list[str] = []
    fake.subscribe(lambda e: order.append(e.kind))
    req = fake.request(root)
    req.add_done_callback(lambda _r: order.append("done"))
    assert fake.complete(req, _frame())
    assert order == [EventKind.MATERIALIZED, "done"]
    assert fake.is_cached(root)
    summary = fake.summary(root)
    assert summary is not None
    assert summary.n_rows == 3


def test_fake_session_stale_result_not_cached() -> None:
    fake = FakeSession()
    _root, a, _ = _tree(fake)
    req = fake.request(a)
    fake.update(a, rows.Head.record(n=3))
    assert req.is_stale()
    fake.complete(req, _frame())
    assert not fake.is_cached(a)
    assert EventKind.MATERIALIZED not in [e.kind for e in fake.events]


# --- JobRunner ---------------------------------------------------------------------------


def test_jobrunner_one_live_request_per_slot() -> None:
    fake = FakeSession()
    _root, a, b = _tree(fake)
    pump = Pump()
    jobs = JobRunner(fake, pump)
    seen: list[str | None] = []
    first = jobs.request("current", a, lambda r: seen.append(r.node_id))
    second = jobs.request("current", b, lambda r: seen.append(r.node_id))
    assert first.cancelled
    assert jobs.running_ids() == {b}
    fake.complete(fake.pending(b)[0], _frame())
    pump.run()
    assert seen == [b]
    assert not jobs.is_running("current")
    assert second.request is not None
    assert second.request.done()
    jobs.shutdown()


def test_jobrunner_drops_stale_and_superseded_results() -> None:
    fake = FakeSession()
    _root, a, _ = _tree(fake)
    pump = Pump()
    jobs = JobRunner(fake, pump)
    seen: list[Any] = []
    jobs.request("current", a, seen.append)
    fake.update(a, rows.Head.record(n=3))  # invalidates a: the running result is stale
    fake.complete(fake.pending(a)[0], _frame())
    pump.run()
    assert seen == []
    assert not jobs.is_running("current")
    jobs.shutdown()


def test_jobrunner_results_from_worker_threads() -> None:
    fake = FakeSession()
    root, *_ = _tree(fake)
    pump = Pump()
    jobs = JobRunner(fake, pump)
    seen: list[Any] = []
    jobs.request("current", root, lambda r: seen.append(r.result()))
    worker = threading.Thread(target=fake.complete, args=(fake.pending(root)[0], _frame(2)))
    worker.start()
    worker.join()
    assert seen == []  # nothing runs on the worker
    pump.run()
    assert len(seen) == 1
    assert len(seen[0]) == 2
    jobs.shutdown()


def test_jobrunner_view_pool_and_listener() -> None:
    fake = FakeSession()
    pump = Pump()
    jobs = JobRunner(fake, pump)
    changes: list[int] = []
    jobs.add_listener(lambda: changes.append(len(jobs)))
    done = threading.Event()
    results: list[Any] = []
    jobs.submit_view("profile", lambda x: x * 2, 21, on_done=lambda f: results.append(f.result()))
    job = jobs.live("profile")
    assert job is not None
    assert job.future is not None
    job.future.add_done_callback(lambda _f: done.set())
    assert done.wait(5)
    while not pump.run():
        pass
    assert results == [42]
    assert changes == [1, 0]
    jobs.shutdown()


def test_jobrunner_preview_slot() -> None:
    fake = FakeSession()
    root, *_ = _tree(fake)
    pump = Pump()
    jobs = JobRunner(fake, pump)
    seen: list[Any] = []
    jobs.request_evaluate("preview", rows.Head.record(n=1), [root], seen.append, head=10)
    (req,) = fake.pending_previews()
    assert req.parent_generations == fake.generations((root,))
    fake.complete(req, _frame(1))
    pump.run()
    assert seen == [req]
    jobs.shutdown()


# --- settings ----------------------------------------------------------------------------


def test_settings_roundtrip(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "s" / "settings.json"
    assert AppSettings.load(path) == AppSettings()
    settings = AppSettings(preview_rows=50, language="de")
    settings.save(path)
    assert AppSettings.load(path) == settings
    path.write_text("{broken", encoding="utf-8")
    assert AppSettings.load(path) == AppSettings()
    with pytest.raises(ValueError, match="preview_rows"):
        AppSettings(preview_rows=0)
