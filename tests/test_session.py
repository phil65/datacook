"""Session: tree edits, events, cache, budget, pinning, threads, previews."""

import threading
import time
from typing import TYPE_CHECKING, Any

import pytest

from datacook.engine import Cancelled, EventKind, OpError, Session
from datacook.engine.ops import code, columns, combine, rows, sources


if TYPE_CHECKING:
    import pandas as pd


def _source(session: Session, n: int = 5, name: str | None = None):
    data = {
        "k": list(range(n)),
        "x": [float(i) for i in range(n)],
        "s": [f"v{i}" for i in range(n)],
    }
    return session.add(sources.InlineData.record(data=data), name=name)


def test_add_validates_inputs(session: Session) -> None:
    src = _source(session)
    with pytest.raises(ValueError, match="2 input"):
        session.add(combine.Merge.record(), [src])
    with pytest.raises(KeyError, match="unknown parent"):
        session.add(rows.Head.record(), ["nope"])
    with pytest.raises(TypeError, match="params"):
        session.add(rows.Head.record(rows.SortRows.Params(by=["k"])), [src])  # ty: ignore[invalid-argument-type]


def test_tree_queries(session: Session) -> None:
    src = _source(session)
    a = session.add(rows.Head.record(n=3), [src])
    b = session.add(rows.SortRows.record(by=["x"], ascending=False), [src])
    m = session.add(combine.Merge.record(on=["k"]), [a, b])
    assert session.roots() == (src,)
    assert [n.id for n in session.children(src.id)] == [a.id, b.id]
    assert set(session.descendants(src.id)) == {a.id, b.id, m.id}
    assert [n.id for n in session.ancestors(m.id)] == [src.id, a.id, b.id, m.id]


def test_materialize_caches_and_shares(session: Session) -> None:
    src = _source(session)
    ren = session.add(columns.RenameColumns.record(columns={"x": "y"}), [src])
    frame = session.materialize(ren.id)
    assert list(frame.columns) == ["k", "y", "s"]
    assert session.materialize(ren.id) is frame
    assert session.is_cached(src.id)
    # rename shares the parent's buffers (copy-on-write): counted once
    used_src_only = session.memory().used
    session.drop(ren.id)
    assert session.memory().used == used_src_only
    summary = session.summary(ren.id)
    assert summary is not None  # summaries survive eviction
    assert (summary.n_rows, summary.n_columns) == (5, 3)
    assert summary.columns[0].dtype == "int64[pyarrow]"


def test_update_invalidates_downstream(session: Session) -> None:
    events: list[Any] = []
    session.subscribe(events.append)
    src = _source(session)
    head = session.add(rows.Head.record(n=3), [src])
    tail = session.add(rows.SortRows.record(by=["k"], ascending=False), [head])
    other = session.add(rows.Head.record(n=1), [src])
    assert len(session.materialize(tail.id)) == 3
    session.materialize(other.id)
    events.clear()
    before = {n.id: n.generation for n in session.nodes()}
    node = session.update(head.id, params=rows.Head.Params(n=4))
    assert node.generation > max(before.values())
    assert session[tail.id].generation > before[tail.id]
    assert session[src.id].generation == before[src.id]
    assert [e.kind for e in events] == [EventKind.CHANGED, EventKind.INVALIDATED]
    assert set(events[1].node_ids) == {head.id, tail.id}
    assert session.is_cached(src.id)
    assert session.is_cached(other.id)
    assert not session.is_cached(tail.id)
    assert session.summary(tail.id) is None
    assert len(session.materialize(tail.id)) == 4
    # name change: no invalidation
    events.clear()
    session.update(head.id, name="first rows")
    assert [e.kind for e in events] == [EventKind.CHANGED]
    assert session.is_cached(tail.id)


def test_remove_subtree(session: Session) -> None:
    events: list[Any] = []
    src = _source(session)
    a = session.add(rows.Head.record(n=3), [src])
    b = session.add(rows.Head.record(n=2), [a])
    session.materialize(b.id)
    session.subscribe(events.append)
    assert set(session.remove(a.id)) == {a.id, b.id}
    assert events[0].kind is EventKind.REMOVED
    assert len(session) == 1
    assert session.children(src.id) == ()
    assert set(session.cached_ids()) == {src.id}


def test_events_materialized_and_error(session: Session) -> None:
    events: list[Any] = []
    session.subscribe(events.append)
    src = _source(session)
    bad = session.add(rows.FilterRows.record(expr="missing_column > 1"), [src])
    with pytest.raises(OpError, match="filter_rows"):
        session.materialize(bad.id)
    kinds = [e.kind for e in events]
    assert kinds == [EventKind.ADDED, EventKind.ADDED, EventKind.MATERIALIZED, EventKind.ERROR]
    assert events[-1].node_id == bad.id
    assert session.error(bad.id) is events[-1].error
    session.update(bad.id, params=rows.FilterRows.Params(expr="k > 1"))
    assert session.error(bad.id) is None
    assert len(session.materialize(bad.id)) == 3


def test_callback_errors_are_logged(session: Session, caplog) -> None:
    def broken(event) -> None:
        raise RuntimeError("boom")

    unsubscribe = session.subscribe(broken)
    _source(session)
    assert "callback failed" in caplog.text
    unsubscribe()
    caplog.clear()
    _source(session)
    assert "callback failed" not in caplog.text


def test_budget_evicts_lru_but_not_pinned() -> None:
    with Session(memory_budget=10**9) as session:
        src = _source(session, n=10_000)
        heads = [
            session.add(rows.SortRows.record(by=["x"], ascending=bool(i % 2)), [src])
            for i in range(4)
        ]
        session.pin(src.id)
        for h in heads:
            session.materialize(h.id)
        full = session.memory().used
        events: list[Any] = []
        session.subscribe(events.append)
        session.set_memory_budget(full // 2)
        assert session.memory().used <= full // 2
        assert session.is_cached(src.id)  # pinned
        assert not session.is_cached(heads[0].id)  # least recently used
        assert session.is_cached(heads[-1].id)
        assert events[0].kind is EventKind.EVICTED
        session.unpin(src.id)
        session.set_memory_budget(0)
        assert session.cached_ids() == ()
        # evicted nodes are recomputed on demand
        assert len(session.materialize(heads[0].id)) == 10_000


def _slow_code(seconds: float) -> str:
    return f"import time\ntime.sleep({seconds})\ndf = df.head(2)"


def test_concurrent_requests_compute_once(session: Session) -> None:
    src = _source(session)
    slow = session.add(code.CustomCode.record(code=_slow_code(0.2)), [src])
    computed: list[str] = []
    session.subscribe(
        lambda e: computed.append(e.node_id) if e.kind is EventKind.MATERIALIZED else None
    )
    results: list[pd.DataFrame] = []
    threads = [
        threading.Thread(target=lambda: results.append(session.materialize(slow.id)))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert computed.count(slow.id) == 1
    assert all(r is results[0] for r in results)


@pytest.mark.parametrize("round_", range(20))
def test_concurrent_requests_compute_once_stress(round_: int) -> None:
    """Many threads hit the same uncached chain at once; every node is computed once."""
    with Session() as session:
        src = _source(session, n=50)
        slow = session.add(code.CustomCode.record(code=_slow_code(0.01)), [src])
        tail = session.add(rows.SortRows.record(by=["k"], ascending=False), [slow])
        counts: dict[str, int] = {}
        lock = threading.Lock()

        def on_event(event) -> None:
            if event.kind is EventKind.MATERIALIZED:
                with lock:
                    counts[event.node_id] = counts.get(event.node_id, 0) + 1

        session.subscribe(on_event)
        barrier = threading.Barrier(8)
        results: list[pd.DataFrame] = []

        def run() -> None:
            barrier.wait()
            results.append(session.materialize(tail.id if round_ % 2 else slow.id))

        threads = [threading.Thread(target=run) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(results) == 8
        assert all(r is results[0] for r in results)
        assert set(counts.values()) == {1}


def test_concurrent_failure_computed_once(session: Session) -> None:
    """Waiters on a failing computation get its exception instead of computing again."""
    src = _source(session)
    bad = session.add(code.CustomCode.record(code=_slow_code(0.2) + "\nraise ValueError"), [src])
    errors: list[BaseException] = []
    failed: list[str] = []
    session.subscribe(lambda e: failed.append(e.node_id) if e.kind is EventKind.ERROR else None)

    def run() -> None:
        try:
            session.materialize(bad.id)
        except OpError as e:
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 4
    assert failed == [bad.id]


def test_waiter_computes_after_cancelled_request(session: Session) -> None:
    """A thread waiting on a request that gets cancelled computes the node itself."""
    src = _source(session)
    slow = session.add(code.CustomCode.record(code=_slow_code(0.2)), [src])
    after = session.add(rows.Head.record(n=1), [slow])
    request = session.request(after.id)
    time.sleep(0.05)  # the worker is in the slow step
    results: list[pd.DataFrame] = []
    waiter = threading.Thread(target=lambda: results.append(session.materialize(after.id)))
    waiter.start()
    time.sleep(0.05)
    request.cancel()
    waiter.join(timeout=10)
    assert len(results) == 1
    assert len(results[0]) == 1
    assert session.is_cached(after.id)


def test_generations_are_never_reused(session: Session) -> None:
    """A node re-added with the same id (undo of a delete) gets a fresh generation."""
    src = _source(session)
    head = session.add(rows.Head.record(n=3), [src])
    request = session.request(head.id)
    request.result(timeout=10)
    assert not request.is_stale()
    old_generation = head.generation
    session.remove(head.id)
    assert request.is_stale()
    again = session.add(rows.Head.record(n=3), [src], node_id=head.id)
    assert again.generation > old_generation
    assert request.is_stale()  # a result from before the removal never looks current
    gens = [n.generation for n in session.nodes()]
    assert len(set(gens)) == len(gens)


def test_request_evaluate_staleness(session: Session) -> None:
    src = _source(session)
    head = session.add(rows.Head.record(n=3), [src])
    other = session.add(rows.Head.record(n=1), [src])
    preview = session.request_evaluate(rows.Head.record(n=2), [head])
    assert len(preview.result(timeout=10)) == 2
    assert preview.parent_generations == {head.id: head.generation}
    assert not preview.is_stale()
    session.update(other.id, params=rows.Head.Params(n=2))  # unrelated edit
    assert not preview.is_stale()
    session.update(src.id, name="renamed")  # name only: data unchanged
    assert not preview.is_stale()
    session.update(src.id, params=sources.InlineData.Params(data={"k": [1]}))
    assert preview.is_stale()  # an ancestor of the preview's parent changed
    fresh = session.request_evaluate(rows.Head.record(n=2), [head.id])
    fresh.result(timeout=10)
    assert not fresh.is_stale()
    session.remove(head.id)
    assert fresh.is_stale()
    with pytest.raises(KeyError, match="unknown parent"):
        session.request_evaluate(rows.Head.record(n=2), ["nope"])


def test_long_op_does_not_block_readers(session: Session) -> None:
    """No op runs under the session lock: getters stay fast while a worker computes."""
    src = _source(session)
    slow = session.add(code.CustomCode.record(code=_slow_code(1.0)), [src])
    session.materialize(src.id)
    request = session.request(slow.id)
    time.sleep(0.1)  # the worker is inside the slow op now
    durations: list[float] = []

    def reader() -> None:
        while not request.done():
            t0 = time.perf_counter()
            session.get(slow.id)
            session.summary(src.id)
            session.summary(slow.id)
            session.error(slow.id)
            session.memory()
            session.is_cached(src.id)
            session.code()
            durations.append(time.perf_counter() - t0)
            time.sleep(0.01)

    thread = threading.Thread(target=reader)
    thread.start()
    thread.join()
    request.result(timeout=10)
    durations.sort()
    assert len(durations) > 10
    assert durations[len(durations) // 2] < 0.005  # median
    assert durations[-1] < 0.2  # blocked behind the op would be ~1 s


def test_concurrent_reads_of_one_frame(session: Session) -> None:
    """Several threads slice the same cached frame (copy-on-write reference tracking)."""
    src = _source(session, n=5_000)
    ren = session.add(columns.RenameColumns.record(columns={"x": "y"}), [src])
    session.materialize(ren.id)
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def run(offset: int) -> None:
        barrier.wait()
        try:
            for i in range(200):
                start = (offset * 37 + i * 13) % 4_900
                part = session.window(ren.id, start, start + 100, ["k", "y"])
                assert part["k"].iloc[0] == start
                assert len(part) == 100
                session.window(src.id, start, start + 10)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_request_on_worker_and_staleness(session: Session) -> None:
    src = _source(session)
    slow = session.add(code.CustomCode.record(code=_slow_code(0.3)), [src])
    threads: list[str] = []
    source_done = threading.Event()

    def on_event(event) -> None:
        threads.append(threading.current_thread().name)
        if event.kind is EventKind.MATERIALIZED and event.node_id == src.id:
            source_done.set()

    session.subscribe(on_event)
    request = session.request(slow.id)
    assert source_done.wait(10)  # the worker is in the slow step now
    session.update(
        src.id, params=sources.InlineData.Params(data={"k": [1], "x": [1.0], "s": ["a"]})
    )
    frame = request.result(timeout=10)
    assert len(frame) == 2  # computed for the old generation
    assert request.is_stale()
    assert not session.is_cached(slow.id)  # stale results are not cached
    fresh = session.request(slow.id)
    assert len(fresh.result(timeout=10)) == 1
    assert not fresh.is_stale()
    assert any(name.startswith("datacook-session") for name in threads)


def test_request_cancel(session: Session) -> None:
    src = _source(session)
    slow = session.add(code.CustomCode.record(code=_slow_code(0.3)), [src])
    after = session.add(rows.Head.record(n=1), [slow])
    request = session.request(after.id)
    time.sleep(0.05)
    request.cancel()
    with pytest.raises((Cancelled, Exception)):
        request.result(timeout=10)
    assert request.cancelled
    assert not session.is_cached(after.id)


def test_evaluate_preview_does_not_touch_tree(session: Session) -> None:
    src = _source(session)
    head = session.add(rows.Head.record(n=3), [src])
    committed = session.materialize(head.id)
    events: list[Any] = []
    session.subscribe(events.append)
    preview = session.evaluate(rows.Head.record(n=4), head.parents)
    assert len(preview) == 4
    assert session.materialize(head.id) is committed
    assert len(session) == 2
    assert events == []
    window = session.evaluate(rows.SortRows.record(by=["k"], ascending=False), [src], head=2)
    assert window["k"].tolist() == [4, 3]
    assert session.request_evaluate(rows.Head.record(n=1), [src]).result(timeout=10).shape == (1, 3)


def test_window(session: Session) -> None:
    src = _source(session, n=100)
    part = session.window(src.id, 10, 15, ["k"])
    assert part["k"].tolist() == [10, 11, 12, 13, 14]


def test_concurrent_edits_and_materialization() -> None:
    """Workers materialise while the tree is edited; results always match a generation."""
    with Session(memory_budget=200_000) as session:
        src = _source(session, n=2_000)
        chain = [src]
        for i in range(6):
            chain.append(session.add(rows.Head.record(n=1_900 - i), [chain[-1]]))
        errors: list[BaseException] = []
        stop = threading.Event()

        def worker() -> None:
            while not stop.is_set():
                try:
                    for node in chain[1:]:
                        before = session[node.id].generation
                        frame = session.materialize(node.id)
                        after = session[node.id]
                        if before == after.generation:
                            assert len(frame) <= after.record.params.n  # ty: ignore[unresolved-attribute]
                except Exception as e:  # noqa: BLE001
                    errors.append(e)
                    return

        workers = [threading.Thread(target=worker) for _ in range(4)]
        for w in workers:
            w.start()
        for i in range(30):
            session.update(chain[1].id, params=rows.Head.Params(n=1_000 + i))
            time.sleep(0.002)
        stop.set()
        for w in workers:
            w.join()
        assert errors == []
        assert session.memory().used <= 200_000 or len(session.cached_ids()) <= 1
        assert len(session.materialize(chain[-1].id)) == 1_029
