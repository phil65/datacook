"""Process-wide allocator setup, so that dropped frames give their memory back to the OS.

Measured (3M x 7 frame, 4 steps, then "Free memory"; DATACOOK_PLAN.md, phase 3 memory
note): after the drop only the cached frames are alive, but with the defaults ~450 MiB of
freed memory stays resident:

- pyarrow's default pool (mimalloc; jemalloc in some builds) keeps freed pages until
  `release_unused()`.
- With the system pool, glibc serves column buffers from its heaps: its mmap threshold
  grows dynamically (up to 32 MiB) after the first large free, and `malloc_trim` does not
  shrink the heaps of worker-thread arenas.

`configure()` makes Arrow use the system allocator and pins glibc's mmap threshold, so every
buffer from 1 MiB up is its own mapping and is unmapped as soon as its last reference dies.
`release()` returns what is left in the allocators' free lists. Cost: ~15 % slower on
allocation-heavy ops (fresh pages are faulted in again).

This module does not import pyarrow at import time: Arrow reads `ARROW_DEFAULT_MEMORY_POOL`
when pyarrow is imported, and `pa.set_memory_pool()` only covers the Python bindings (C++
internals such as the Parquet reader keep using the pool chosen at import).
"""

import ctypes
import ctypes.util
import functools
import os
import sys


MMAP_THRESHOLD = 1 << 20
"""glibc: allocations from 1 MiB up get their own mapping."""

POOL_ENV = "ARROW_DEFAULT_MEMORY_POOL"
_M_MMAP_THRESHOLD = -3  # glibc malloc.h


@functools.cache
def _glibc() -> ctypes.CDLL | None:
    if not sys.platform.startswith("linux"):
        return None
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6")
        libc.mallopt  # noqa: B018  (musl has neither)
        libc.malloc_trim  # noqa: B018
    except OSError, AttributeError:
        return None
    return libc


def configure(mmap_threshold: int = MMAP_THRESHOLD) -> None:
    """Set up the allocators for a long-lived process; call before pyarrow is imported.

    Explicit settings win: a set `ARROW_DEFAULT_MEMORY_POOL` keeps the chosen Arrow pool,
    a set `MALLOC_MMAP_THRESHOLD_` keeps glibc's threshold. Calling it again is harmless.
    """
    if POOL_ENV not in os.environ:
        os.environ[POOL_ENV] = "system"
        if "pyarrow" in sys.modules:  # too late for Arrow's C++ default: Python side only
            import pyarrow as pa

            pa.set_memory_pool(pa.system_memory_pool())
    libc = _glibc()
    if libc is not None and "MALLOC_MMAP_THRESHOLD_" not in os.environ:
        libc.mallopt(_M_MMAP_THRESHOLD, mmap_threshold)


def release() -> None:
    """Give memory freed by dropped frames back to the OS (Arrow pools, glibc heaps)."""
    if "pyarrow" in sys.modules:
        import pyarrow as pa

        for get_pool in (pa.default_memory_pool, pa.mimalloc_memory_pool, pa.jemalloc_memory_pool):
            try:
                pool = get_pool()
            except NotImplementedError:  # allocator not in this build
                continue
            pool.release_unused()
    libc = _glibc()
    if libc is not None:
        libc.malloc_trim(0)
