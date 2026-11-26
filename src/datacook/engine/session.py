"""Session: the node tree plus on-demand materialisation under a memory budget.

Event and threading contract (the app's views build on this):

- **State.** The tree is a dict of immutable `Node` snapshots, replaced on every edit. All
  tree and cache state is guarded by one lock (`threading.RLock`); there is no module-level
  mutable state, so a session works the same with or without the GIL. Getters return
  snapshots (nodes, tuples), safe to keep on any thread.
- **Generations.** Each node has a `generation` that changes whenever its data changes
  (its params or an ancestor's params were edited). Generations come from one session-wide
  monotonic counter, so a value is never reused: a node removed and re-added with the same
  id (undo of a delete) gets a new one. Results are tagged with the generation they were
  computed for; a result whose generation is no longer current is *stale*: it is not cached
  and no `MATERIALIZED` event is sent for it. `Request.is_stale()` tells a view to drop a
  late result (for previews: if one of the parents changed).
- **Events.** `subscribe(callback)` registers a plain callable that receives `Event`s:
  ADDED, REMOVED (node + descendants), CHANGED (params/name/comment), MOVED (new parents,
  `reparent` / `remove_step`), INVALIDATED (edited or moved node + descendants),
  MATERIALIZED (node, generation), EVICTED (memory budget), ERROR (node, exception).
  Callbacks run synchronously on the thread that caused the event (a worker thread for
  materialisation) and never while the lock is held, so they may call back into the
  session. A GUI must marshal them to its own thread (e.g. a queued Qt signal).
  Exceptions in callbacks are logged, not raised.
- **Materialisation.** `materialize(node_id)` computes synchronously on the calling
  thread (parents first, from the cache where possible). Concurrent requests for the same
  node and generation share one computation (waiters get its frame or its exception).
  `request(node_id)` runs it on the session's executor and returns a `Request` (a future
  with cooperative cancellation: checked between steps of a chain, an op that already runs
  finishes first).
- **Lock scope.** The lock is held only for dict / cache bookkeeping, never while an op
  runs, a reader does IO, a frame is measured or code is generated, so getters (`get`,
  `summary`, `error`, `memory`, ...) stay O(1)-ish for a GUI thread while workers compute.
- **Cache.** LRU under `memory_budget` bytes; shared copy-on-write buffers are counted once.
  Pinned nodes (`pin`/`unpin`, e.g. the selected node and its parent) are not evicted.
  Summaries (shape, schema, bytes) survive eviction until the node's generation changes.
- **Previews.** `evaluate(record, parents)` computes a candidate op (e.g. a params form
  with unsaved edits) on committed parents without touching the tree or caching the result;
  `request_evaluate` does the same on the executor; its `Request.is_stale()` is true once a
  parent was edited or removed after the request was made.
"""

import concurrent.futures
from dataclasses import dataclass
import logging
import os
import threading
from typing import TYPE_CHECKING, Any, Self

from datacook.engine import codegen, frames, node as node_mod
from datacook.engine.cache import FrameCache
from datacook.engine.events import Event, EventKind
from datacook.engine.ops import OpError, default_ops


if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from datacook.engine.frames import Frame, FrameSummary
    from datacook.engine.node import Node
    from datacook.engine.ops import Op, OpRecord, Params
    from datacook.engine.registry import Registry


logger = logging.getLogger(__name__)

type Callback = Callable[[Event], Any]


class Cancelled(Exception):  # noqa: N818
    """A request was cancelled."""


def default_budget() -> int:
    """25 % of physical memory (2 GiB if it cannot be determined)."""
    try:
        total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except AttributeError, ValueError, OSError:
        return 2 * 2**30
    return max(total // 4, 256 * 2**20)


@dataclass(frozen=True, slots=True)
class MemoryStats:
    used: int
    budget: int
    cached_nodes: int
    pinned_nodes: int


class _Token:
    """Cooperative cancellation flag."""

    __slots__ = ("_event",)

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise Cancelled


class Request:
    """Handle for an asynchronous materialisation (see `Session.request`)."""

    def __init__(
        self,
        session: Session,
        node_id: str | None,
        generation: int | None,
        future: concurrent.futures.Future[Frame],
        token: _Token,
        parent_generations: Mapping[str, int] | None = None,
    ) -> None:
        self.session = session
        self.node_id = node_id
        self.generation = generation
        self.parent_generations = dict(parent_generations or {})
        """For previews (`request_evaluate`): the parents' generations at request time."""
        self.future = future
        self._token = token

    def cancel(self) -> None:
        self._token.cancel()
        self.future.cancel()

    @property
    def cancelled(self) -> bool:
        return self._token.cancelled

    def done(self) -> bool:
        return self.future.done()

    def result(self, timeout: float | None = None) -> Frame:
        return self.future.result(timeout)

    def is_stale(self) -> bool:
        """True if the node (for previews: a parent) changed or was removed since the request."""
        expected = dict(self.parent_generations)
        if self.node_id is not None and self.generation is not None:
            expected[self.node_id] = self.generation
        current = self.session.generations(expected)
        return any(current.get(nid) != gen for nid, gen in expected.items())

    def add_done_callback(self, fn: Callable[[Request], Any]) -> None:
        self.future.add_done_callback(lambda _f: fn(self))


@dataclass(slots=True)
class _Inflight:
    """One running computation of a node; waiters read its outcome after `done`."""

    generation: int
    done: threading.Event
    frame: Frame | None = None
    error: BaseException | None = None


class Session:
    def __init__(
        self,
        *,
        memory_budget: int | None = None,
        registry: Registry[type[Op]] | None = None,
        executor: concurrent.futures.Executor | None = None,
    ) -> None:
        self.registry = registry if registry is not None else default_ops()
        self._lock = threading.RLock()
        self._nodes: dict[str, Node] = {}
        self._children: dict[str, list[str]] = {}
        self._cache = FrameCache(memory_budget if memory_budget is not None else default_budget())
        self._summaries: dict[str, tuple[int, FrameSummary]] = {}
        self._errors: dict[str, tuple[int, BaseException]] = {}
        self._inflight: dict[str, _Inflight] = {}
        self._generation = 0  # session-wide counter, see `_next_generation`
        self._callbacks: tuple[Callback, ...] = ()
        self._executor = executor
        self._own_executor = False

    # --- lifecycle ---------------------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            executor, own = self._executor, self._own_executor
            self._executor, self._own_executor = None, False
            self._cache.clear()
        if executor is not None and own:
            executor.shutdown(wait=True, cancel_futures=True)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def executor(self) -> concurrent.futures.Executor:
        with self._lock:
            if self._executor is None:
                self._executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=2, thread_name_prefix="datacook-session"
                )
                self._own_executor = True
            return self._executor

    # --- events ------------------------------------------------------------------------
    def subscribe(self, callback: Callback) -> Callable[[], None]:
        """Register an event callback; returns a function that unsubscribes it."""
        with self._lock:
            self._callbacks = (*self._callbacks, callback)

        def unsubscribe() -> None:
            with self._lock:
                self._callbacks = tuple(c for c in self._callbacks if c is not callback)

        return unsubscribe

    def _emit(self, *events: Event) -> None:
        callbacks = self._callbacks
        for event in events:
            for callback in callbacks:
                try:
                    callback(event)
                except Exception:
                    logger.exception("session event callback failed: %s", event)

    # --- tree --------------------------------------------------------------------------
    def get(self, node_id: str) -> Node | None:
        with self._lock:
            return self._nodes.get(node_id)

    def generations(self, node_ids: Iterable[str]) -> dict[str, int]:
        """Current generation of each existing node in `node_ids` (one consistent snapshot)."""
        with self._lock:
            return {nid: n.generation for nid in node_ids if (n := self._nodes.get(nid))}

    def _next_generation(self) -> int:
        """A generation never handed out before in this session (call under the lock)."""
        self._generation += 1
        return self._generation

    def __getitem__(self, node_id: str) -> Node:
        with self._lock:
            return self._nodes[node_id]

    def __contains__(self, node_id: object) -> bool:
        with self._lock:
            return node_id in self._nodes

    def __len__(self) -> int:
        with self._lock:
            return len(self._nodes)

    def nodes(self) -> tuple[Node, ...]:
        """All nodes, parents before children (insertion order)."""
        with self._lock:
            return tuple(self._nodes.values())

    def roots(self) -> tuple[Node, ...]:
        with self._lock:
            return tuple(n for n in self._nodes.values() if not n.parents)

    def children(self, node_id: str) -> tuple[Node, ...]:
        with self._lock:
            return tuple(self._nodes[c] for c in self._children.get(node_id, ()))

    def descendants(self, node_id: str) -> tuple[str, ...]:
        """Ids of all nodes depending on `node_id` (breadth first, without it)."""
        with self._lock:
            return tuple(self._descendants(node_id))

    def _descendants(self, node_id: str) -> list[str]:
        seen: dict[str, None] = {}
        queue = list(self._children.get(node_id, ()))
        while queue:
            nid = queue.pop(0)
            if nid not in seen:
                seen[nid] = None
                queue.extend(self._children.get(nid, ()))
        return list(seen)

    def ancestors(self, node_id: str) -> tuple[Node, ...]:
        """The node and everything it depends on, parents before children."""
        with self._lock:
            order: dict[str, None] = {}

            def visit(nid: str) -> None:
                if nid in order:
                    return
                for p in self._nodes[nid].parents:
                    visit(p)
                order[nid] = None

            visit(node_id)
            return tuple(self._nodes[n] for n in order)

    def op(self, node: Node | str) -> type[Op]:
        record = (self[node] if isinstance(node, str) else node).record
        return self.registry[record.op_id]

    def add(
        self,
        record: OpRecord,
        parents: Sequence[Node | str] = (),
        *,
        name: str | None = None,
        comment: str | None = None,
        node_id: str | None = None,
    ) -> Node:
        op = self.registry[record.op_id]
        parent_ids = tuple(p if isinstance(p, str) else p.id for p in parents)
        if not op.takes(len(parent_ids)):
            msg = f"{op.id} takes {op.inputs_text()} input(s), got {len(parent_ids)}"
            raise ValueError(msg)
        if not isinstance(record.params, op.Params):
            msg = f"params of {op.id} must be {op.Params.__qualname__}"
            raise TypeError(msg)
        with self._lock:
            missing = [p for p in parent_ids if p not in self._nodes]
            if missing:
                msg = f"unknown parent node(s): {missing}"
                raise KeyError(msg)
            nid = node_id or node_mod.new_id()
            if nid in self._nodes:
                msg = f"node id {nid!r} exists"
                raise ValueError(msg)
            node = node_mod.Node(
                nid,
                record,
                parent_ids,
                name=name,
                comment=comment,
                generation=self._next_generation(),
            )
            self._nodes[nid] = node
            self._children[nid] = []
            for p in parent_ids:
                self._children[p].append(nid)
        self._emit(Event(EventKind.ADDED, (nid,), node.generation))
        return node

    def update(
        self,
        node_id: str,
        record: OpRecord | None = None,
        *,
        params: Params | None = None,
        name: str | None = None,
        comment: str | None = None,
    ) -> Node:
        """Edit a node. New params invalidate it and all its descendants."""
        events: list[Event] = []
        with self._lock:
            node = self._nodes[node_id]
            if params is not None:
                record = type(node.record)(node.record.op_id, params)
            changes: dict[str, Any] = {}
            if name is not None:
                changes["name"] = name or None
            if comment is not None:
                changes["comment"] = comment or None
            invalidated: list[str] = []
            if record is not None and record != node.record:
                op = self.registry[record.op_id]
                if not op.takes(len(node.parents)) or not isinstance(record.params, op.Params):
                    msg = f"record does not fit node {node_id} ({op.id})"
                    raise ValueError(msg)
                changes["record"] = record
                invalidated = [node_id, *self._descendants(node_id)]
            if not changes:
                return node
            for nid in invalidated:
                n = self._nodes[nid]
                self._nodes[nid] = n.evolve(generation=self._next_generation())
                self._cache.discard(nid)
                self._summaries.pop(nid, None)
                self._errors.pop(nid, None)
            node = self._nodes[node_id].evolve(**changes)
            self._nodes[node_id] = node
            events.append(Event(EventKind.CHANGED, (node_id,), node.generation))
            if invalidated:
                events.append(Event(EventKind.INVALIDATED, tuple(invalidated), node.generation))
        self._emit(*events)
        return node

    def remove(self, node_id: str) -> tuple[str, ...]:
        """Remove a node and all its descendants; returns the removed ids."""
        with self._lock:
            removed = (node_id, *self._descendants(node_id))
            for nid in removed:
                node = self._nodes.pop(nid)
                self._children.pop(nid, None)
                for p in node.parents:
                    if p in self._children:
                        self._children[p].remove(nid)
                self._cache.discard(nid)
                self._summaries.pop(nid, None)
                self._errors.pop(nid, None)
        self._emit(Event(EventKind.REMOVED, removed))
        return removed

    def reparent(self, node_id: str, parents: Sequence[Node | str]) -> Node:
        """Give a node new parents (as many as before); invalidates it and its descendants.

        The node and its descendants move behind their new parents in `nodes()` order if
        needed, so "parents before children" still holds.
        """
        parent_ids = tuple(p if isinstance(p, str) else p.id for p in parents)
        with self._lock:
            node = self._nodes[node_id]
            if len(parent_ids) != len(node.parents):
                msg = f"{node.op_id} takes {len(node.parents)} input(s), got {len(parent_ids)}"
                raise ValueError(msg)
            missing = [p for p in parent_ids if p not in self._nodes]
            if missing:
                msg = f"unknown parent node(s): {missing}"
                raise KeyError(msg)
            descendants = self._descendants(node_id)
            if node_id in parent_ids or set(parent_ids) & set(descendants):
                msg = f"re-parenting {node_id} would create a cycle"
                raise ValueError(msg)
            if parent_ids == node.parents:
                return node
            for p in dict.fromkeys(node.parents):
                self._children[p] = [c for c in self._children[p] if c != node_id]
            for p in dict.fromkeys(parent_ids):
                self._children[p].append(node_id)
            self._nodes[node_id] = node.evolve(parents=parent_ids)
            invalidated = [node_id, *descendants]
            self._move_behind_parents(node_id, invalidated)
            for nid in invalidated:
                self._nodes[nid] = self._nodes[nid].evolve(generation=self._next_generation())
                self._cache.discard(nid)
                self._summaries.pop(nid, None)
                self._errors.pop(nid, None)
            node = self._nodes[node_id]
        self._emit(
            Event(EventKind.MOVED, (node_id,), node.generation),
            Event(EventKind.INVALIDATED, tuple(invalidated), node.generation),
        )
        return node

    def _move_behind_parents(self, node_id: str, subtree: Sequence[str]) -> None:
        """Keep insertion order topological: move `subtree` to the end if a parent is later."""
        order = {nid: i for i, nid in enumerate(self._nodes)}
        if all(order[p] < order[node_id] for p in self._nodes[node_id].parents):
            return
        members = set(subtree)
        for nid in [n for n in self._nodes if n in members]:  # keeps their relative order
            self._nodes[nid] = self._nodes.pop(nid)

    def remove_step(self, node_id: str) -> Node:
        """Delete one step and hand its children to its parent; returns the removed node.

        Raises `restructure.StepError` for sources, merges and (when the parent's schema is
        known) children that use columns the parent does not have.
        """
        from datacook.engine import restructure

        parent = restructure.check_remove_step(self, node_id)
        node = self[node_id]
        for child in self.children(node_id):
            self.reparent(child.id, [parent if p == node_id else p for p in child.parents])
        self.remove(node_id)
        return node

    def clear(self) -> None:
        for root in self.roots():
            if root.id in self:
                self.remove(root.id)

    # --- cache -------------------------------------------------------------------------
    @property
    def memory_budget(self) -> int:
        return self._cache.budget

    def set_memory_budget(self, budget: int) -> None:
        with self._lock:
            evicted = self._cache.set_budget(budget)
        self._emit_evicted(evicted)

    def memory(self) -> MemoryStats:
        with self._lock:
            keys = self._cache.keys()
            pinned = sum(1 for k in self._nodes if self._cache.is_pinned(k))
            return MemoryStats(self._cache.used, self._cache.budget, len(keys), pinned)

    def cached_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._cache.keys())

    def is_cached(self, node_id: str) -> bool:
        with self._lock:
            node = self._nodes.get(node_id)
            return node is not None and self._cache.get(node_id, node.generation) is not None

    def pin(self, node_id: str) -> None:
        """Keep the node's frame in the cache (counted pins)."""
        with self._lock:
            self._cache.pin(node_id)

    def unpin(self, node_id: str) -> None:
        with self._lock:
            evicted = self._cache.unpin(node_id)
        self._emit_evicted(evicted)

    def drop(self, node_id: str) -> None:
        """Drop a node's cached frame (it is recomputed on demand)."""
        with self._lock:
            dropped = self._cache.discard(node_id)
        if dropped:
            self._emit_evicted([node_id])

    def _emit_evicted(self, evicted: Sequence[str]) -> None:
        if evicted:
            self._emit(Event(EventKind.EVICTED, tuple(evicted)))

    # --- results -----------------------------------------------------------------------
    def summary(self, node_id: str) -> FrameSummary | None:
        """Shape, schema and size of the node's frame, if it was computed (no compute)."""
        with self._lock:
            node = self._nodes.get(node_id)
            entry = self._summaries.get(node_id)
            if node is None or entry is None or entry[0] != node.generation:
                return None
            return entry[1]

    def error(self, node_id: str) -> BaseException | None:
        """The exception of the last failed computation of the node's current generation."""
        with self._lock:
            node = self._nodes.get(node_id)
            entry = self._errors.get(node_id)
            if node is None or entry is None or entry[0] != node.generation:
                return None
            return entry[1]

    def window(
        self,
        node_id: str,
        start: int,
        stop: int,
        columns: Sequence[str] | None = None,
    ) -> Frame:
        """Rows `start:stop` of the node's frame (computes it if needed)."""
        return frames.window(self.materialize(node_id), start, stop, columns)

    def materialize(self, node_id: str) -> Frame:
        """The node's frame, from the cache or computed on this thread."""
        return self._materialize(node_id, None)

    def _materialize(self, node_id: str, token: _Token | None) -> Frame:
        while True:
            with self._lock:
                node = self._nodes[node_id]
                frame = self._cache.get(node_id, node.generation)
                if frame is not None:
                    return frame
                inflight = self._inflight.get(node_id)
                if inflight is None or inflight.generation != node.generation:
                    inflight = _Inflight(node.generation, threading.Event())
                    self._inflight[node_id] = inflight
                    break
            # another thread computes the same node and generation: wait for its outcome
            while not inflight.done.wait(0.05):
                if token is not None:
                    token.check()
            if inflight.frame is not None:
                return inflight.frame
            if isinstance(inflight.error, OpError):
                # a new exception per waiter: tracebacks are not shared between threads
                raise OpError(*inflight.error.args) from inflight.error
            if inflight.error is not None:
                raise inflight.error
            # the computing thread was cancelled: look again (and maybe compute ourselves)
        try:
            frame = self._compute(node, token)
        except Cancelled:
            self._abandon(node_id, inflight)
            raise
        except Exception as e:
            with self._lock:
                fresh = self._is_current(node)
                if fresh:
                    self._errors[node_id] = (node.generation, e)
                inflight.error = e
                self._release(node_id, inflight)
            inflight.done.set()
            if fresh:
                self._emit(Event(EventKind.ERROR, (node_id,), node.generation, e))
            raise
        except BaseException:  # SystemExit from custom code, KeyboardInterrupt, ...
            self._abandon(node_id, inflight)
            raise
        # measure outside the lock (walks every column / buffer)
        buffers = frames.buffers(frame)
        summary = frames.summary(frame, buffers)
        evicted: list[str] = []
        with self._lock:
            # cache the result *before* waiters wake up, in one locked section with
            # releasing the in-flight entry, so nobody sees neither and computes again
            fresh = self._is_current(node)
            if fresh:
                evicted = self._cache.put(node_id, node.generation, frame, buffers)
                self._summaries[node_id] = (node.generation, summary)
                self._errors.pop(node_id, None)
            inflight.frame = frame
            self._release(node_id, inflight)
        inflight.done.set()
        if fresh:
            self._emit(Event(EventKind.MATERIALIZED, (node_id,), node.generation))
        self._emit_evicted(evicted)
        return frame

    def _compute(self, node: Node, token: _Token | None) -> Frame:
        inputs = [self._materialize(p, token) for p in node.parents]
        if token is not None:
            token.check()
        return self._apply(node.record, inputs)

    def _is_current(self, node: Node) -> bool:
        current = self._nodes.get(node.id)
        return current is not None and current.generation == node.generation

    def _abandon(self, node_id: str, inflight: _Inflight) -> None:
        """End a computation without an outcome: waiters look again (and may compute)."""
        with self._lock:
            self._release(node_id, inflight)
        inflight.done.set()

    def _release(self, node_id: str, inflight: _Inflight) -> None:
        if self._inflight.get(node_id) is inflight:
            del self._inflight[node_id]

    def _apply(self, record: OpRecord, inputs: Sequence[Frame]) -> Frame:
        op = self.registry[record.op_id]
        args = [frames.ensure_backend(f, op.backend) for f in inputs]
        try:
            return op.apply(record.params, *args)
        except OpError:
            raise
        except Exception as e:
            raise OpError(f"{op.id}: {type(e).__name__}: {e}") from e

    def request(self, node_id: str) -> Request:
        """Materialise on the executor; returns a cancellable handle."""
        with self._lock:
            generation = self._nodes[node_id].generation
        token = _Token()
        future = self.executor.submit(self._materialize, node_id, token)
        return Request(self, node_id, generation, future, token)

    def evaluate(
        self,
        record: OpRecord,
        parents: Sequence[Node | str] = (),
        *,
        head: int | None = None,
    ) -> Frame:
        """Compute a candidate op on committed parents (preview); nothing is stored."""
        return self._evaluate(record, parents, head, None)

    def _evaluate(
        self,
        record: OpRecord,
        parents: Sequence[Node | str],
        head: int | None,
        token: _Token | None,
    ) -> Frame:
        ids = [p if isinstance(p, str) else p.id for p in parents]
        inputs = [self._materialize(p, token) for p in ids]
        if token is not None:
            token.check()
        result = self._apply(record, inputs)
        return result if head is None else frames.window(result, 0, head)

    def request_evaluate(
        self,
        record: OpRecord,
        parents: Sequence[Node | str] = (),
        *,
        head: int | None = None,
    ) -> Request:
        ids = [p if isinstance(p, str) else p.id for p in parents]
        with self._lock:
            missing = [p for p in ids if p not in self._nodes]
            if missing:
                msg = f"unknown parent node(s): {missing}"
                raise KeyError(msg)
            generations = {p: self._nodes[p].generation for p in ids}
        token = _Token()
        future = self.executor.submit(self._evaluate, record, ids, head, token)
        return Request(self, None, None, future, token, generations)

    # --- code --------------------------------------------------------------------------
    def code(self, node_ids: Iterable[str] | None = None) -> str:
        """Python script computing the given nodes (default: the whole tree)."""
        return self.render_code(node_ids).text

    def render_code(self, node_ids: Iterable[str] | None = None) -> codegen.Script:
        """Script plus the line span of each node's block (`codegen.render`)."""
        with self._lock:
            nodes = dict(self._nodes)
        return codegen.render(nodes, self.registry, targets=node_ids)

    def import_script(self, text: str) -> list[Node]:
        """Parse a script (see `parser.parse`) and add its steps as new nodes."""
        from datacook.engine import parser

        parsed = parser.parse(text, self.registry)
        created: list[Node] = []
        for step in parsed.steps:
            parents = [created[i] for i in step.parents]
            created.append(self.add(step.record, parents, name=step.name))
        return created
