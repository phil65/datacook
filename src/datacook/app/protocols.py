"""What the app uses of the engine: `SessionLike` / `RequestLike` (Qt-free).

`datacook.engine.Session` satisfies both protocols; `datacook.app.testing.FakeSession` does
too, so controllers can be tested with requests the test resolves in any order.
"""

from typing import TYPE_CHECKING, Any, Protocol


if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from datacook.engine import Event, FrameSummary, MemoryStats, Node, Op, OpRecord, Params
    from datacook.engine.codegen import Script
    from datacook.engine.frames import Frame
    from datacook.engine.registry import Registry


class RequestLike(Protocol):
    """A cancellable asynchronous computation (`datacook.engine.Request`)."""

    @property
    def node_id(self) -> str | None: ...

    @property
    def generation(self) -> int | None: ...

    @property
    def cancelled(self) -> bool: ...

    def cancel(self) -> None: ...

    def done(self) -> bool: ...

    def result(self, timeout: float | None = None) -> Frame: ...

    def is_stale(self) -> bool: ...

    def add_done_callback(self, fn: Callable[[Any], Any]) -> None: ...


class SessionLike(Protocol):
    """The subset of `datacook.engine.Session` the app uses (see its module docstring)."""

    @property
    def registry(self) -> Registry[type[Op]]: ...

    # events
    def subscribe(self, callback: Callable[[Event], Any]) -> Callable[[], None]: ...

    # tree (lock-protected snapshots, cheap on the GUI thread)
    def get(self, node_id: str) -> Node | None: ...

    def generations(self, node_ids: Iterable[str]) -> dict[str, int]: ...

    def __contains__(self, node_id: object) -> bool: ...

    def __len__(self) -> int: ...

    def nodes(self) -> tuple[Node, ...]: ...

    def roots(self) -> tuple[Node, ...]: ...

    def children(self, node_id: str) -> tuple[Node, ...]: ...

    def descendants(self, node_id: str) -> tuple[str, ...]: ...

    def ancestors(self, node_id: str) -> tuple[Node, ...]: ...

    # mutations (GUI thread only, through `CommandController`)
    def add(
        self,
        record: OpRecord,
        parents: Sequence[Node | str] = (),
        *,
        name: str | None = None,
        comment: str | None = None,
        node_id: str | None = None,
    ) -> Node: ...

    def update(
        self,
        node_id: str,
        record: OpRecord | None = None,
        *,
        params: Params | None = None,
        name: str | None = None,
        comment: str | None = None,
    ) -> Node: ...

    def remove(self, node_id: str) -> tuple[str, ...]: ...

    def reparent(self, node_id: str, parents: Sequence[Node | str]) -> Node: ...

    def remove_step(self, node_id: str) -> Node: ...

    # cache / memory
    def memory(self) -> MemoryStats: ...

    def set_memory_budget(self, budget: int) -> None: ...

    def cached_ids(self) -> tuple[str, ...]: ...

    def is_cached(self, node_id: str) -> bool: ...

    def pin(self, node_id: str) -> None: ...

    def unpin(self, node_id: str) -> None: ...

    def drop(self, node_id: str) -> None: ...

    # results
    def summary(self, node_id: str) -> FrameSummary | None: ...

    def error(self, node_id: str) -> BaseException | None: ...

    def materialize(self, node_id: str) -> Frame: ...

    def request(self, node_id: str) -> RequestLike: ...

    def request_evaluate(
        self,
        record: OpRecord,
        parents: Sequence[Node | str] = (),
        *,
        head: int | None = None,
    ) -> RequestLike: ...

    # code
    def render_code(self, node_ids: Iterable[str] | None = None) -> Script: ...
