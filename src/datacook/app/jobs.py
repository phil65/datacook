"""JobRunner: background work per view slot (Qt-free).

- **Executors.** The compute pool is the session's executor (`Session(executor=...)`):
  `request` / `request_evaluate` run there. A separate view pool runs cheap view work
  (column statistics, prefetch), so a slow op never blocks scrolling or profiling.
- **Slots.** At most one live job per slot name ("current", "preview", "profile",
  "reader-preview", ...). Starting a job in a slot cancels the previous one (engine requests:
  cooperative cancellation between steps; a running op finishes and its result is dropped).
- **Delivery.** Done callbacks fire on a worker thread; the runner only forwards them through
  `post` (the bridge queue), so `on_done` runs on the GUI thread, *after* the engine events of
  the same computation. `on_done` is called only for the slot's live job, not cancelled and
  (for engine requests) not stale: superseded, cancelled and stale results are dropped here.
- **Threading.** Every method except the internal done hook is for the GUI thread only; the
  runner's own state is never touched from a worker.
"""

import concurrent.futures
from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from datacook.app.protocols import RequestLike, SessionLike
    from datacook.engine import Node, OpRecord


logger = logging.getLogger(__name__)

type Post = Callable[..., None]
"""`post(fn, *args)`: run `fn(*args)` on the GUI thread (thread-safe)."""


@dataclass(eq=False, slots=True)
class Job:
    """A live job of a slot: an engine request or a view-pool future."""

    slot: str
    request: RequestLike | None = None
    future: concurrent.futures.Future[Any] | None = None
    node_ids: tuple[str, ...] = ()
    """Nodes this job computes (for "computing" badges)."""
    meta: dict[str, Any] = field(default_factory=dict)

    def cancel(self) -> None:
        if self.request is not None:
            self.request.cancel()
        if self.future is not None:
            self.future.cancel()

    @property
    def cancelled(self) -> bool:
        if self.request is not None:
            return self.request.cancelled
        return self.future is not None and self.future.cancelled()


class JobRunner:
    def __init__(
        self,
        session: SessionLike,
        post: Post,
        *,
        view_executor: concurrent.futures.Executor | None = None,
        view_threads: int = 2,
    ) -> None:
        self.session = session
        self._post = post
        self._own_view = view_executor is None
        self.view_executor = view_executor or concurrent.futures.ThreadPoolExecutor(
            max_workers=view_threads, thread_name_prefix="datacook-view"
        )
        self._live: dict[str, Job] = {}
        self._listeners: list[Callable[[], None]] = []
        self._closed = False

    # --- starting jobs -----------------------------------------------------------------
    def request(
        self,
        slot: str,
        node_id: str,
        on_done: Callable[[RequestLike], Any],
    ) -> Job:
        """Materialise `node_id` for `slot` (cancels the slot's previous job)."""
        self.cancel(slot, notify=False)
        job = Job(slot, request=self.session.request(node_id), node_ids=(node_id,))
        self._start(job, on_done)
        return job

    def request_evaluate(
        self,
        slot: str,
        record: OpRecord,
        parents: Sequence[Node | str],
        on_done: Callable[[RequestLike], Any],
        *,
        head: int | None = None,
    ) -> Job:
        """Preview a candidate op on committed parents for `slot`."""
        self.cancel(slot, notify=False)
        req = self.session.request_evaluate(record, parents, head=head)
        ids = tuple(p if isinstance(p, str) else p.id for p in parents)
        job = Job(slot, request=req, node_ids=ids)
        self._start(job, on_done)
        return job

    def submit_view(
        self,
        slot: str,
        fn: Callable[..., Any],
        *args: Any,
        on_done: Callable[[concurrent.futures.Future[Any]], Any],
    ) -> Job:
        """Run `fn(*args)` on the view pool for `slot`; `on_done(future)` on the GUI thread."""
        self.cancel(slot, notify=False)
        job = Job(slot, future=self.view_executor.submit(fn, *args))
        self._start(job, on_done)
        return job

    def _start(self, job: Job, on_done: Callable[[Any], Any]) -> None:
        if self._closed:
            job.cancel()
            return
        self._live[job.slot] = job
        handle: Any = job.request if job.request is not None else job.future
        # worker thread (or this thread if already done): only post, never touch state
        handle.add_done_callback(lambda _h: self._post(self._finish, job, on_done))
        self._notify()

    def _finish(self, job: Job, on_done: Callable[[Any], Any]) -> None:
        """GUI thread: deliver the result if the job is still the slot's live one."""
        if self._live.get(job.slot) is not job:
            return  # superseded or cancelled; its cache entry (if fresh) is not lost
        del self._live[job.slot]
        self._notify()
        if job.cancelled:
            return
        if job.request is not None:
            if job.request.is_stale():
                logger.debug("dropping stale result of slot %s", job.slot)
                return
            on_done(job.request)
        else:
            on_done(job.future)

    # --- control -----------------------------------------------------------------------
    def cancel(self, slot: str, *, notify: bool = True) -> None:
        job = self._live.pop(slot, None)
        if job is not None:
            job.cancel()
            if notify:
                self._notify()

    def cancel_all(self) -> None:
        for slot in list(self._live):
            self.cancel(slot)

    def live(self, slot: str) -> Job | None:
        return self._live.get(slot)

    def is_running(self, slot: str) -> bool:
        return slot in self._live

    def running_ids(self) -> frozenset[str]:
        """Nodes some live engine request computes (inputs, for previews)."""
        return frozenset(
            n for j in self._live.values() if j.request is not None for n in j.node_ids
        )

    def __len__(self) -> int:
        return len(self._live)

    def add_listener(self, fn: Callable[[], None]) -> None:
        """`fn()` runs (GUI thread) whenever the set of live jobs changes."""
        self._listeners.append(fn)

    def _notify(self) -> None:
        for fn in self._listeners:
            fn()

    def shutdown(self) -> None:
        self._closed = True
        self.cancel_all()
        if self._own_view:
            self.view_executor.shutdown(wait=False, cancel_futures=True)
