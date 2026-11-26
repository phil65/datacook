"""Test helpers: `FakeSession` (Qt-free).

`FakeSession` implements `protocols.SessionLike` with the engine's tree semantics (immutable
`Node` snapshots, session-wide generations, the same events in the same order) but computes
nothing: `request()` / `request_evaluate()` return `FakeRequest`s that stay pending until
the test resolves them with `complete()` / `fail()`, in any order and from any thread.
Like the engine, a fresh result is cached and announced (`MATERIALIZED`) *before* its future
resolves, and a result for an outdated generation is neither cached nor announced.
"""

import collections
import concurrent.futures
import threading
from typing import TYPE_CHECKING, Any

from datacook.engine import Cancelled, Event, EventKind, MemoryStats, Node, default_ops
from datacook.engine.codegen import Script
from datacook.engine.node import new_id


if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from datacook.engine import FrameSummary, Op, OpRecord, Params
    from datacook.engine.frames import Frame
    from datacook.engine.registry import Registry


class FakeRequest:
    def __init__(
        self,
        session: FakeSession,
        node_id: str | None,
        generation: int | None,
        parent_generations: dict[str, int] | None = None,
        record: OpRecord | None = None,
    ) -> None:
        self.session = session
        self.node_id = node_id
        self.generation = generation
        self.parent_generations = dict(parent_generations or {})
        self.record = record
        """For previews: the evaluated record."""
        self.future: concurrent.futures.Future[Frame] = concurrent.futures.Future()
        self._cancelled = threading.Event()

    def __repr__(self) -> str:
        what = self.node_id or f"evaluate({self.record and self.record.op_id})"
        return f"FakeRequest({what}, gen={self.generation})"

    def cancel(self) -> None:
        self._cancelled.set()
        self.future.cancel()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def done(self) -> bool:
        return self.future.done()

    def result(self, timeout: float | None = None) -> Frame:
        try:
            return self.future.result(timeout)
        except concurrent.futures.CancelledError:
            raise Cancelled from None

    def is_stale(self) -> bool:
        expected = dict(self.parent_generations)
        if self.node_id is not None and self.generation is not None:
            expected[self.node_id] = self.generation
        current = self.session.generations(expected)
        return any(current.get(nid) != gen for nid, gen in expected.items())

    def add_done_callback(self, fn: Callable[[FakeRequest], Any]) -> None:
        self.future.add_done_callback(lambda _f: fn(self))


class FakeSession:
    """In-memory `SessionLike`; see module docstring. Thread-safe like the engine."""

    def __init__(self, registry: Registry[type[Op]] | None = None) -> None:
        self._registry = registry if registry is not None else default_ops()
        self._lock = threading.RLock()
        self._nodes: dict[str, Node] = {}
        self._children: dict[str, list[str]] = {}
        self._generation = 0
        self._cache: dict[str, tuple[int, Frame]] = {}
        self._summaries: dict[str, tuple[int, FrameSummary]] = {}
        self._errors: dict[str, tuple[int, BaseException]] = {}
        self._pins: collections.Counter[str] = collections.Counter()
        self._callbacks: tuple[Callable[[Event], Any], ...] = ()
        self.budget = 2**30
        self.requests: list[FakeRequest] = []
        """Every request made, in order (resolved ones included)."""
        self.events: list[Event] = []
        """Every event emitted, in order."""

    @property
    def registry(self) -> Registry[type[Op]]:
        return self._registry

    # --- events ------------------------------------------------------------------------
    def subscribe(self, callback: Callable[[Event], Any]) -> Callable[[], None]:
        with self._lock:
            self._callbacks = (*self._callbacks, callback)

        def unsubscribe() -> None:
            with self._lock:
                self._callbacks = tuple(c for c in self._callbacks if c is not callback)

        return unsubscribe

    def _emit(self, *events: Event) -> None:
        with self._lock:
            self.events.extend(events)
            callbacks = self._callbacks
        for event in events:
            for callback in callbacks:
                callback(event)

    def _next_generation(self) -> int:
        self._generation += 1
        return self._generation

    # --- tree --------------------------------------------------------------------------
    def get(self, node_id: str) -> Node | None:
        with self._lock:
            return self._nodes.get(node_id)

    def __getitem__(self, node_id: str) -> Node:
        with self._lock:
            return self._nodes[node_id]

    def generations(self, node_ids: Iterable[str]) -> dict[str, int]:
        with self._lock:
            return {nid: n.generation for nid in node_ids if (n := self._nodes.get(nid))}

    def __contains__(self, node_id: object) -> bool:
        with self._lock:
            return node_id in self._nodes

    def __len__(self) -> int:
        with self._lock:
            return len(self._nodes)

    def nodes(self) -> tuple[Node, ...]:
        with self._lock:
            return tuple(self._nodes.values())

    def roots(self) -> tuple[Node, ...]:
        with self._lock:
            return tuple(n for n in self._nodes.values() if not n.parents)

    def children(self, node_id: str) -> tuple[Node, ...]:
        with self._lock:
            return tuple(self._nodes[c] for c in self._children.get(node_id, ()))

    def descendants(self, node_id: str) -> tuple[str, ...]:
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

    def add(
        self,
        record: OpRecord,
        parents: Sequence[Node | str] = (),
        *,
        name: str | None = None,
        comment: str | None = None,
        node_id: str | None = None,
    ) -> Node:
        parent_ids = tuple(p if isinstance(p, str) else p.id for p in parents)
        with self._lock:
            missing = [p for p in parent_ids if p not in self._nodes]
            if missing:
                msg = f"unknown parent node(s): {missing}"
                raise KeyError(msg)
            nid = node_id or new_id()
            if nid in self._nodes:
                msg = f"node id {nid!r} exists"
                raise ValueError(msg)
            node = Node(
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
                changes["record"] = record
                invalidated = [node_id, *self._descendants(node_id)]
            if not changes:
                return node
            for nid in invalidated:
                self._nodes[nid] = self._nodes[nid].evolve(generation=self._next_generation())
                self._cache.pop(nid, None)
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
        with self._lock:
            removed = (node_id, *self._descendants(node_id))
            for nid in removed:
                node = self._nodes.pop(nid)
                self._children.pop(nid, None)
                for p in node.parents:
                    if p in self._children:
                        self._children[p].remove(nid)
                self._cache.pop(nid, None)
                self._summaries.pop(nid, None)
                self._errors.pop(nid, None)
        self._emit(Event(EventKind.REMOVED, removed))
        return removed

    def reparent(self, node_id: str, parents: Sequence[Node | str]) -> Node:
        parent_ids = tuple(p if isinstance(p, str) else p.id for p in parents)
        with self._lock:
            node = self._nodes[node_id]
            if len(parent_ids) != len(node.parents):
                msg = f"{node.op_id} takes {len(node.parents)} input(s), got {len(parent_ids)}"
                raise ValueError(msg)
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
            order = {nid: i for i, nid in enumerate(self._nodes)}
            if any(order[p] > order[node_id] for p in parent_ids):
                members = set(invalidated)
                for nid in [n for n in self._nodes if n in members]:
                    self._nodes[nid] = self._nodes.pop(nid)
            for nid in invalidated:
                self._nodes[nid] = self._nodes[nid].evolve(generation=self._next_generation())
                self._cache.pop(nid, None)
                self._summaries.pop(nid, None)
                self._errors.pop(nid, None)
            node = self._nodes[node_id]
        self._emit(
            Event(EventKind.MOVED, (node_id,), node.generation),
            Event(EventKind.INVALIDATED, tuple(invalidated), node.generation),
        )
        return node

    def remove_step(self, node_id: str) -> Node:
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
    def memory(self) -> MemoryStats:
        with self._lock:
            pinned = sum(1 for k in self._nodes if self._pins[k] > 0)
            return MemoryStats(0, self.budget, len(self._cache), pinned)

    def set_memory_budget(self, budget: int) -> None:
        self.budget = budget

    def cached_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._cache)

    def is_cached(self, node_id: str) -> bool:
        with self._lock:
            node = self._nodes.get(node_id)
            entry = self._cache.get(node_id)
            return node is not None and entry is not None and entry[0] == node.generation

    def pin(self, node_id: str) -> None:
        with self._lock:
            self._pins[node_id] += 1

    def unpin(self, node_id: str) -> None:
        with self._lock:
            if self._pins[node_id] <= 1:
                self._pins.pop(node_id, None)
            else:
                self._pins[node_id] -= 1

    def pin_counts(self) -> dict[str, int]:
        with self._lock:
            return {k: v for k, v in self._pins.items() if v > 0}

    def drop(self, node_id: str) -> None:
        with self._lock:
            dropped = self._cache.pop(node_id, None) is not None
        if dropped:
            self._emit(Event(EventKind.EVICTED, (node_id,)))

    def evict(self, *node_ids: str) -> tuple[str, ...]:
        """Simulate budget eviction: drop unpinned cached frames, emit EVICTED."""
        with self._lock:
            evicted = tuple(n for n in node_ids if n in self._cache and self._pins[n] <= 0)
            for nid in evicted:
                del self._cache[nid]
        if evicted:
            self._emit(Event(EventKind.EVICTED, evicted))
        return evicted

    # --- results -----------------------------------------------------------------------
    def summary(self, node_id: str) -> FrameSummary | None:
        with self._lock:
            node = self._nodes.get(node_id)
            entry = self._summaries.get(node_id)
            if node is None or entry is None or entry[0] != node.generation:
                return None
            return entry[1]

    def error(self, node_id: str) -> BaseException | None:
        with self._lock:
            node = self._nodes.get(node_id)
            entry = self._errors.get(node_id)
            if node is None or entry is None or entry[0] != node.generation:
                return None
            return entry[1]

    def materialize(self, node_id: str) -> Frame:
        """Only cache hits (the fake computes nothing)."""
        with self._lock:
            node = self._nodes[node_id]
            entry = self._cache.get(node_id)
            if entry is None or entry[0] != node.generation:
                msg = f"FakeSession: {node_id} is not cached (resolve a request instead)"
                raise LookupError(msg)
            return entry[1]

    def put(self, node_id: str, frame: Frame) -> None:
        """Cache a frame for the node's current generation and emit MATERIALIZED."""
        with self._lock:
            node = self._nodes[node_id]
            self._store(node, frame)
        self._emit(Event(EventKind.MATERIALIZED, (node_id,), node.generation))

    def _store(self, node: Node, frame: Frame) -> None:
        from datacook.engine import frames

        self._cache[node.id] = (node.generation, frame)
        if frames.is_frame(frame):
            self._summaries[node.id] = (node.generation, frames.summary(frame))
        self._errors.pop(node.id, None)

    def request(self, node_id: str) -> FakeRequest:
        with self._lock:
            req = FakeRequest(self, node_id, self._nodes[node_id].generation)
            self.requests.append(req)
        return req

    def request_evaluate(
        self,
        record: OpRecord,
        parents: Sequence[Node | str] = (),
        *,
        head: int | None = None,
    ) -> FakeRequest:
        ids = [p if isinstance(p, str) else p.id for p in parents]
        with self._lock:
            missing = [p for p in ids if p not in self._nodes]
            if missing:
                msg = f"unknown parent node(s): {missing}"
                raise KeyError(msg)
            gens = {p: self._nodes[p].generation for p in ids}
            req = FakeRequest(self, None, None, gens, record)
            self.requests.append(req)
        return req

    # --- test controls -----------------------------------------------------------------
    def pending(self, node_id: str | None = None) -> list[FakeRequest]:
        """Unresolved, not cancelled requests (for `node_id`; previews: `node_id=None`)."""
        with self._lock:
            return [
                r
                for r in self.requests
                if not r.done() and not r.cancelled and (node_id is None or r.node_id == node_id)
            ]

    def pending_previews(self) -> list[FakeRequest]:
        with self._lock:
            return [r for r in self.requests if r.record and not r.done() and not r.cancelled]

    def complete(self, request: FakeRequest, frame: Frame) -> bool:
        """Resolve a request (any thread). False if it was cancelled before."""
        if not request.future.set_running_or_notify_cancel():
            return False
        if request.node_id is not None:
            with self._lock:
                node = self._nodes.get(request.node_id)
                fresh = node is not None and node.generation == request.generation
                if fresh and node is not None:
                    self._store(node, frame)
            if fresh:
                self._emit(Event(EventKind.MATERIALIZED, (request.node_id,), request.generation))
        request.future.set_result(frame)
        return True

    def fail(self, request: FakeRequest, exc: BaseException, failing: str | None = None) -> bool:
        """Fail a request; the error is recorded for `failing` (default: the request's node)."""
        if not request.future.set_running_or_notify_cancel():
            return False
        failing = failing or request.node_id
        event: Event | None = None
        if failing is not None:
            with self._lock:
                node = self._nodes.get(failing)
                if node is not None:
                    self._errors[failing] = (node.generation, exc)
                    event = Event(EventKind.ERROR, (failing,), node.generation, exc)
            if event is not None:
                self._emit(event)
        request.future.set_exception(exc)
        return True

    # --- code --------------------------------------------------------------------------
    def render_code(self, node_ids: Iterable[str] | None = None) -> Script:
        with self._lock:
            nodes = list(self._nodes.values())
        wanted = None if node_ids is None else set(node_ids)
        lines: list[str] = []
        spans: dict[str, tuple[int, int]] = {}
        for node in nodes:
            if wanted is None or node.id in wanted:
                lines.append(f"# {node.name or node.op_id}")
                spans[node.id] = (len(lines), len(lines))
        return Script("\n".join(lines) + "\n", spans)
