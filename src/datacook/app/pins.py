"""Pin bookkeeping for the memory policy (Qt-free, GUI thread only).

The engine counts pins per node; `PinBook` keeps track of which *owner* (a view slot such as
"current" or "preview") pinned what, so pins are always released exactly once. Memory
invariant of the app: a view holds a full frame only for a node that is pinned
(`held_ids ⊆ pinned_ids`, see `AppController.held_ids`).
"""

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Iterable

    from datacook.app.protocols import SessionLike


class PinBook:
    def __init__(self, session: SessionLike) -> None:
        self._session = session
        self._owners: dict[str, tuple[str, ...]] = {}

    def set(self, owner: str, node_ids: Iterable[str]) -> None:
        """Replace the pins of `owner` (new pins first, so a kept node never drops to 0)."""
        new = tuple(dict.fromkeys(n for n in node_ids if n in self._session))
        old = self._owners.get(owner, ())
        for nid in new:
            self._session.pin(nid)
        if new:
            self._owners[owner] = new
        else:
            self._owners.pop(owner, None)
        for nid in old:
            self._session.unpin(nid)

    def release(self, owner: str) -> None:
        self.set(owner, ())

    def release_all(self) -> None:
        for owner in list(self._owners):
            self.release(owner)

    def forget(self, node_ids: Iterable[str]) -> None:
        """Unpin removed nodes (the engine keeps pin counts by id, also for removed ids)."""
        gone = set(node_ids)
        for owner, ids in list(self._owners.items()):
            if not gone.intersection(ids):
                continue
            kept = tuple(n for n in ids if n not in gone)
            if kept:
                self._owners[owner] = kept
            else:
                del self._owners[owner]
            for nid in ids:
                if nid in gone:
                    self._session.unpin(nid)

    def owned(self, owner: str) -> tuple[str, ...]:
        return self._owners.get(owner, ())

    def pinned_ids(self) -> frozenset[str]:
        return frozenset(n for ids in self._owners.values() for n in ids)

    def owners(self) -> dict[str, tuple[str, ...]]:
        return dict(self._owners)
