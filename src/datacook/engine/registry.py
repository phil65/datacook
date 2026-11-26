"""Entry-point registries for ops (`datacook.ops`) and writers (`datacook.writers`).

Built-in ops and writers are registered through the package's own entry points, exactly
like third-party plugins. A registry loads its group once (thread-safe) and can also take
explicit classes (tests, embedding).
"""

import threading
from typing import TYPE_CHECKING, Any, Protocol

from epregistry import EntryPointRegistry


if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator


OPS_GROUP = "datacook.ops"
WRITERS_GROUP = "datacook.writers"


class HasId(Protocol):
    id: str


class Registry[T: HasId]:
    def __init__(self, group: str | None, items: Iterable[T] = ()) -> None:
        self.group = group
        self._lock = threading.Lock()
        self._items: dict[str, T] = {}
        self._loaded = group is None
        for item in items:
            self.register(item)

    def _ensure_loaded(self) -> dict[str, T]:
        if not self._loaded:
            with self._lock:
                if not self._loaded:
                    assert self.group is not None
                    loaded: dict[str, Any] = EntryPointRegistry[Any](self.group).load_all()
                    for name, item in loaded.items():
                        if item.id != name:
                            msg = f"entry point {name!r} in {self.group} loads {item.id!r}"
                            raise ValueError(msg)
                        self._items.setdefault(name, item)
                    self._loaded = True
        return self._items

    def register(self, item: T, *, replace: bool = False) -> T:
        with self._lock:
            if not replace and item.id in self._items and self._items[item.id] is not item:
                msg = f"{item.id!r} is already registered"
                raise ValueError(msg)
            self._items[item.id] = item
        return item

    def get(self, item_id: str) -> T:
        try:
            return self._ensure_loaded()[item_id]
        except KeyError:
            msg = f"unknown {self.group or 'item'}: {item_id!r}"
            raise KeyError(msg) from None

    __getitem__ = get

    def __contains__(self, item_id: object) -> bool:
        return item_id in self._ensure_loaded()

    def __iter__(self) -> Iterator[T]:
        return iter(list(self._ensure_loaded().values()))

    def __len__(self) -> int:
        return len(self._ensure_loaded())

    def ids(self) -> list[str]:
        return list(self._ensure_loaded())
