"""Event-flow tests: one per sequence diagram of DATACOOK_APP_DESIGN.md §3 (+ §4 / §5).

FakeSession requests stay pending until the test resolves them; `drain()` delivers the
bridge queue like the Qt event loop would.
"""

from typing import TYPE_CHECKING

from datacook import allocator
from datacook.app.slots import SlotState
from datacook.engine import OpError
from datacook.engine.ops import combine, rows, sources
from tests.app.conftest import check_invariant, drain, frame


if TYPE_CHECKING:
    import pytest

    from datacook.app.controllers import AppController
    from datacook.app.testing import FakeSession


def _chain(app: AppController) -> tuple[str, str, str]:
    """Root -> a -> b, added through commands (undoable)."""
    root = app.commands.add_node(sources.InlineData.record(data={"a": [1, 2, 3]}))
    a = app.commands.add_node(rows.Head.record(n=2), [root])
    b = app.commands.add_node(rows.Head.record(n=1), [a])
    drain(app)
    return root, a, b


# --- select node -------------------------------------------------------------------------


def test_select_uncached_node_computes_on_worker(app: AppController, fake: FakeSession) -> None:
    root, a, _ = _chain(app)
    states: list[str] = []
    app.nodes.slot.state_changed.connect(states.append)
    app.state.current = a
    # pins move at once: the node and its parent
    assert app.pins.owned("current") == (a, root)
    assert app.nodes.slot.state == SlotState.LOADING
    (req,) = fake.pending(a)
    fake.complete(req, frame(2))
    drain(app)
    slot = app.nodes.slot
    assert slot.state == SlotState.READY
    assert slot.node_id == a
    assert slot.frame is not None
    assert len(slot.frame) == 2
    assert slot.generation == fake.generations((a,))[a]
    assert states == ["loading", "ready"]
    check_invariant(app)


def test_select_cached_node_is_immediate(app: AppController, fake: FakeSession) -> None:
    root, *_ = _chain(app)
    fake.put(root, frame())
    drain(app)
    app.state.current = root
    assert app.nodes.slot.state == SlotState.READY
    assert fake.pending() == []
    assert app.nodes.slot.frame is fake.materialize(root)  # the cached frame, no copy
    check_invariant(app)


def test_done_callback_comes_after_materialized(app: AppController, fake: FakeSession) -> None:
    root, *_ = _chain(app)
    order: list[str] = []
    app.bridge.nodes_materialized.connect(lambda _ids: order.append("materialized"))
    app.state.current = root
    (req,) = fake.pending(root)
    req.add_done_callback(lambda _r: app.bridge.post(order.append, "done"))
    fake.complete(req, frame())
    drain(app)
    assert order == ["materialized", "done"]


def test_selection_debounce(qtbot, app: AppController, fake: FakeSession) -> None:
    _root, a, b = _chain(app)
    app.state.update_settings(selection_debounce_ms=30)
    app.state.current = a
    app.state.current = b
    assert fake.pending() == []  # nothing started while the user is still moving
    qtbot.waitUntil(lambda: bool(fake.pending()), timeout=2000)
    assert [r.node_id for r in fake.pending()] == [b]


# --- rapid selection changes -------------------------------------------------------------


def test_rapid_selection_shows_only_last(app: AppController, fake: FakeSession) -> None:
    root, a, b = _chain(app)
    for nid in (root, a, b):
        app.state.current = nid
    # every new selection cancelled the previous request; pins follow the selection
    assert [r.node_id for r in fake.requests if r.cancelled] == [root, a]
    assert app.pins.owned("current") == (b, a)
    assert fake.pin_counts() == {b: 1, a: 1}
    # a late result of a cancelled request is not shown (and not even delivered)
    fake.complete(fake.requests[0], frame(9))
    (live,) = fake.pending(b)
    fake.complete(live, frame(1))
    drain(app)
    assert app.nodes.slot.node_id == b
    assert app.nodes.slot.frame is not None
    assert len(app.nodes.slot.frame) == 1
    check_invariant(app)


def test_result_for_previous_selection_is_dropped(app: AppController, fake: FakeSession) -> None:
    root, a, _ = _chain(app)
    app.state.current = a
    (req_a,) = fake.pending(a)
    app.state.current = root
    (req_root,) = fake.pending(root)
    # the engine finishes the cancelled op anyway (it was already running)
    req_a.cancel()
    fake.complete(req_root, frame(3))
    drain(app)
    assert app.nodes.slot.node_id == root
    assert app.nodes.slot.state == SlotState.READY


# --- preview edit + commit ---------------------------------------------------------------


def test_preview_edit_then_commit(app: AppController, fake: FakeSession) -> None:
    root, a, _ = _chain(app)
    fake.put(root, frame(3))
    fake.put(a, frame(2))
    drain(app)
    app.state.current = a
    spec = app.preview.start_edit(a)
    assert spec.mode == "edit"
    assert spec.inputs == (root,)
    assert app.pins.owned("preview") == (root,)
    # the form starts with the node's params: preview job #1
    (p1,) = fake.pending_previews()
    # edits while the job runs: latest wins, nothing queued
    app.preview.set_params(rows.Head.Params(n=3))
    app.preview.set_params(rows.Head.Params(n=1))
    assert fake.pending_previews() == [p1]
    fake.complete(p1, frame(2))
    drain(app)
    (p2,) = fake.pending_previews()
    assert p2.record is not None
    assert p2.record.params == rows.Head.Params(n=1)
    fake.complete(p2, frame(1))
    drain(app)
    assert app.state.display == "preview"
    assert app.preview.slot.state == SlotState.READY
    assert app.preview.slot.held_id is None  # a head, not a node's frame
    # same params again: no new job
    app.preview.set_params(rows.Head.Params(n=1))
    assert fake.pending_previews() == []

    assert app.preview.commit() == a
    drain(app)
    # the preview head stays visible until the full result is there
    assert app.state.display == "preview"
    assert app.preview.slot.message
    assert app.nodes.slot.state == SlotState.STALE
    fake.complete(fake.pending(a)[0], frame(1))
    drain(app)
    assert app.state.display == "node"
    assert app.state.preview is None
    assert app.preview.slot.frame is None
    assert app.pins.owned("preview") == ()
    node = fake.get(a)
    assert node is not None
    assert node.record.params == rows.Head.Params(n=1)
    check_invariant(app)
    # one undo step restores the old params
    app.commands.undo()
    node = fake.get(a)
    assert node is not None
    assert node.record.params == rows.Head.Params(n=2)


def test_preview_add_commit_selects_new_node(app: AppController, fake: FakeSession) -> None:
    _root, a, _ = _chain(app)
    app.state.current = a
    app.preview.start_add("head", [a], rows.Head.Params(n=1))
    fake.complete(fake.pending_previews()[0], frame(1))
    drain(app)
    committed: list[str] = []
    app.preview.committed.connect(committed.append)
    new = app.preview.commit()
    assert new is not None
    drain(app)
    assert app.state.current == new
    assert app.state.display == "preview"
    fake.complete(fake.pending(new)[0], frame(1))
    drain(app)
    assert committed == [new]
    assert app.state.display == "node"
    assert app.nodes.slot.node_id == new


def test_preview_reruns_when_input_changes(app: AppController, fake: FakeSession) -> None:
    _root, a, _ = _chain(app)
    app.preview.start_add("head", [a], rows.Head.Params(n=1))
    (p1,) = fake.pending_previews()
    app.commands.edit_params(a, rows.Head.record(n=3))
    drain(app)
    assert p1.cancelled
    (p2,) = fake.pending_previews()
    assert p2.parent_generations == fake.generations((a,))


def test_preview_reloads_when_target_changes(app: AppController, fake: FakeSession) -> None:
    _root, a, _ = _chain(app)
    app.preview.start_edit(a)
    fake.complete(fake.pending_previews()[0], frame(2))
    drain(app)
    app.commands.edit_params(a, rows.Head.record(n=3))  # e.g. from the code pane
    drain(app)
    spec = app.state.preview
    assert spec is not None
    assert spec.params == rows.Head.Params(n=3)
    app.commands.rename(a, "renamed")  # name only: the form keeps its values
    drain(app)
    assert app.state.preview == spec


def test_preview_closes_when_target_removed(app: AppController, fake: FakeSession) -> None:
    _root, a, _ = _chain(app)
    app.preview.start_edit(a)
    app.commands.remove_subtree(a)
    drain(app)
    assert app.state.preview is None
    assert app.pins.pinned_ids() == frozenset()


# --- branch ------------------------------------------------------------------------------


def test_branch_adds_sibling_from_cached_parent(app: AppController, fake: FakeSession) -> None:
    _root, a, b = _chain(app)
    fake.put(a, frame(2))
    app.state.current = a
    drain(app)
    added: list[tuple[str, ...]] = []
    app.bridge.nodes_added.connect(added.append)
    m = app.commands.add_node(rows.Sample.record(n=1), [a])
    drain(app)
    assert added == [(m,)]
    assert [n.id for n in fake.children(a)] == [b, m]
    app.state.current = m
    assert app.pins.owned("current") == (m, a)
    assert fake.is_cached(a)  # pinned parent stays: m is computed from it
    fake.complete(fake.pending(m)[0], frame(1))
    drain(app)
    assert app.nodes.slot.node_id == m
    check_invariant(app)


# --- delete subtree, then undo -----------------------------------------------------------


def test_delete_subtree_then_undo(app: AppController, fake: FakeSession) -> None:
    root, a, b = _chain(app)
    m = app.commands.add_node(combine.Merge.record(on=["a"]), [root, b])
    fake.put(b, frame(1))
    app.state.current = b
    drain(app)
    gens_before = fake.generations((a, b, m))
    removed: list[tuple[str, ...]] = []
    app.bridge.nodes_removed.connect(removed.append)

    app.commands.remove_subtree(a)
    drain(app)
    assert removed == [(a, b, m)]
    assert app.state.current == root  # nearest surviving ancestor
    assert app.pins.owned("current") == (root,)
    assert fake.pin_counts() == {root: 1}
    check_invariant(app)

    added: list[tuple[str, ...]] = []
    app.bridge.nodes_added.connect(added.append)
    app.commands.undo()
    drain(app)
    assert added == [(a, b, m)]  # coalesced into one signal
    restored = fake.generations((a, b, m))
    assert set(restored) == {a, b, m}  # same ids
    assert all(restored[n] > gens_before[n] for n in restored)  # fresh generations
    m_node = fake.get(m)
    assert m_node is not None
    assert m_node.parents == (root, b)
    assert not fake.is_cached(b)  # recomputed on demand
    app.commands.redo()
    drain(app)
    assert a not in fake


# --- load file ---------------------------------------------------------------------------


def test_load_file_adds_root_and_selects_it(app: AppController, fake: FakeSession) -> None:
    record = sources.ReadCsv.record(path="data.csv")
    root = app.commands.add_node(record)
    app.state.current = root
    drain(app)
    assert fake.roots()[0].id == root
    assert app.nodes.slot.state == SlotState.LOADING
    fake.complete(fake.pending(root)[0], frame(5))
    drain(app)
    assert app.nodes.slot.state == SlotState.READY
    assert not app.commands.is_clean()
    app.commands.undo()
    drain(app)
    assert app.state.current is None
    assert app.nodes.slot.state == SlotState.EMPTY


def test_reader_preview_has_no_inputs(app: AppController, fake: FakeSession) -> None:
    app.preview.start_add("read_csv", (), sources.ReadCsv.Params(path="data.csv"))
    (req,) = fake.pending_previews()
    assert req.parent_generations == {}
    fake.complete(req, frame(5))
    drain(app)
    assert app.state.display == "preview"
    root = app.preview.commit()
    assert root is not None
    assert app.state.current == root


# --- eviction while shown ----------------------------------------------------------------


def test_eviction_never_touches_pinned_shown_node(app: AppController, fake: FakeSession) -> None:
    root, a, _ = _chain(app)
    fake.put(root, frame())
    fake.put(a, frame(2))
    app.state.current = a
    drain(app)
    assert fake.evict(root, a) == ()  # both pinned (a + its parent)
    app.state.current = None
    assert fake.evict(root, a) == (root, a)


def test_explicit_drop_of_shown_node(app: AppController, fake: FakeSession) -> None:
    _root, a, _ = _chain(app)
    fake.put(a, frame(2))
    app.state.current = a
    drain(app)
    assert app.free_memory() == ()  # nothing unpinned is cached
    fake.drop(a)  # "Free memory" on the current node
    drain(app)
    slot = app.nodes.slot
    assert slot.state == SlotState.EVICTED
    assert slot.frame is None
    assert fake.pending() == []  # no automatic re-request
    app.nodes.recompute()
    fake.complete(fake.pending(a)[0], frame(2))
    drain(app)
    assert slot.state == SlotState.READY


def test_free_memory_drops_unpinned_and_releases_allocator_memory(
    app: AppController, fake: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, a, b = _chain(app)
    for nid in (root, a, b):
        fake.put(nid, frame())
    app.state.current = b
    drain(app)
    released: list[bool] = []
    monkeypatch.setattr(allocator, "release", lambda: released.append(True))
    assert app.free_memory() == (root,)  # b + its parent a are pinned
    assert released == [True]


def test_invalidated_shown_node_drops_frame(app: AppController, fake: FakeSession) -> None:
    _root, a, b = _chain(app)
    fake.put(b, frame(1))
    app.state.current = b
    drain(app)
    app.commands.edit_params(a, rows.Head.record(n=3))  # an ancestor of the shown node
    drain(app)
    slot = app.nodes.slot
    assert slot.state == SlotState.STALE
    assert slot.frame is None  # not an unbudgeted copy of an outdated frame
    assert slot.summary is not None  # last known shape for "recomputing…"
    (req,) = fake.pending(b)
    assert req.generation == fake.generations((b,))[b]
    fake.complete(req, frame(1))
    drain(app)
    assert slot.state == SlotState.READY


# --- op error ----------------------------------------------------------------------------


def test_error_in_ancestor_is_routed(app: AppController, fake: FakeSession) -> None:
    _root, a, b = _chain(app)
    errors: list[tuple[str, BaseException]] = []
    app.bridge.node_error.connect(lambda nid, exc: errors.append((nid, exc)))
    app.state.current = b
    exc = OpError("head: boom")
    fake.fail(fake.pending(b)[0], exc, failing=a)
    drain(app)
    assert errors == [(a, exc)]
    slot = app.nodes.slot
    assert slot.state == SlotState.ERROR
    assert slot.error is exc
    assert slot.error_node == a  # "Step <a> failed" + [Go to step]
    # selecting the failed step shows its error without recomputing
    app.state.current = a
    assert app.nodes.slot.state == SlotState.ERROR
    assert fake.pending() == []


def test_preview_error_is_shown(app: AppController, fake: FakeSession) -> None:
    root, *_ = _chain(app)
    app.preview.start_add("head", [root], rows.Head.Params(n=1))
    fake.fail(fake.pending_previews()[0], OpError("bad"))
    drain(app)
    assert app.preview.slot.state == SlotState.ERROR
    assert app.state.display == "preview"


# --- lifecycle ---------------------------------------------------------------------------


def test_close_releases_everything(app: AppController, fake: FakeSession) -> None:
    _root, a, _ = _chain(app)
    app.state.current = a
    app.preview.start_add("head", [a], rows.Head.Params(n=1))
    assert fake.pin_counts()
    app.close()
    assert fake.pin_counts() == {}
    assert all(r.cancelled or r.done() for r in fake.requests)
    assert len(app.jobs) == 0


def test_new_project_clears_tree_and_history(app: AppController, fake: FakeSession) -> None:
    _chain(app)
    app.new_project()
    drain(app)
    assert len(fake) == 0
    assert not app.commands.can_undo()
    assert app.commands.is_clean()
