"""LRU frame cache with a memory budget and pinning.

Memory is counted per buffer (`frames.buffers`), so frames sharing data through pandas
copy-on-write (rename, column selection, ...) are counted once. Not thread-safe on its own:
the `Session` guards it with its lock.
"""

from collections import Counter, OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from datacook.engine import frames


if TYPE_CHECKING:
    from datacook.engine.frames import Frame


@dataclass(slots=True)
class _Entry:
    generation: int
    frame: Frame
    buffers: dict[int, int]


class FrameCache:
    def __init__(self, budget: int) -> None:
        self.budget = budget
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._refs: Counter[int] = Counter()
        self._sizes: dict[int, int] = {}
        self._used = 0
        self._pins: Counter[str] = Counter()

    @property
    def used(self) -> int:
        """Bytes held by cached frames (shared buffers counted once)."""
        return self._used

    def __contains__(self, key: str) -> bool:
        return key in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def keys(self) -> list[str]:
        return list(self._entries)

    def get(self, key: str, generation: int) -> Frame | None:
        entry = self._entries.get(key)
        if entry is None or entry.generation != generation:
            return None
        self._entries.move_to_end(key)
        return entry.frame

    def put(
        self,
        key: str,
        generation: int,
        frame: Frame,
        buffers: dict[int, int] | None = None,
    ) -> list[str]:
        """Insert a frame; returns the keys evicted to stay within the budget.

        `buffers` (`frames.buffers(frame)`) can be passed in when measured beforehand, so
        a caller holding a lock does not walk the frame under it.
        """
        self.discard(key)
        entry = _Entry(generation, frame, frames.buffers(frame) if buffers is None else buffers)
        self._entries[key] = entry
        for address, size in entry.buffers.items():
            if self._refs[address] == 0:
                self._sizes[address] = size
                self._used += size
            self._refs[address] += 1
        return self._evict(keep=key)

    def discard(self, key: str) -> bool:
        entry = self._entries.pop(key, None)
        if entry is None:
            return False
        for address in entry.buffers:
            self._refs[address] -= 1
            if self._refs[address] == 0:
                del self._refs[address]
                self._used -= self._sizes.pop(address)
        return True

    def pin(self, key: str) -> None:
        self._pins[key] += 1

    def unpin(self, key: str) -> list[str]:
        if self._pins[key] <= 1:
            self._pins.pop(key, None)
        else:
            self._pins[key] -= 1
        return self._evict()

    def is_pinned(self, key: str) -> bool:
        return self._pins[key] > 0

    def set_budget(self, budget: int) -> list[str]:
        self.budget = budget
        return self._evict()

    def _evict(self, keep: str | None = None) -> list[str]:
        evicted: list[str] = []
        if self._used <= self.budget:
            return evicted
        for key in list(self._entries):  # oldest first
            if self._used <= self.budget:
                break
            if key == keep or self._pins[key] > 0:
                continue
            self.discard(key)
            evicted.append(key)
        return evicted

    def clear(self) -> None:
        for key in list(self._entries):
            self.discard(key)
