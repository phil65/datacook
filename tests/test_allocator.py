"""Allocator setup: Arrow's system pool before pyarrow is imported, explicit settings win."""

import os
import subprocess
import sys

import pyarrow as pa
import pytest

from datacook import allocator


def _run(code: str, **env: str) -> str:
    environ = {k: v for k, v in os.environ.items() if k != allocator.POOL_ENV} | env
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, env=environ
    ).stdout.strip()


POOL = (
    "from datacook import allocator\n"
    "allocator.configure()\n"
    "import pyarrow as pa\n"
    "print(pa.default_memory_pool().backend_name)\n"
)


def test_configure_selects_system_pool_before_pyarrow_import() -> None:
    assert _run(POOL) == "system"


def test_configure_keeps_an_explicit_pool() -> None:
    assert _run(POOL, ARROW_DEFAULT_MEMORY_POOL="mimalloc") == "mimalloc"  # in every wheel


def test_configure_after_pyarrow_import_sets_python_pool() -> None:
    code = "import pyarrow as pa\n" + POOL
    assert _run(code) == "system"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="glibc only")
def test_glibc_is_found_on_linux() -> None:
    assert allocator._glibc() is not None


def test_release_runs() -> None:
    buf = pa.allocate_buffer(1 << 20)
    del buf
    allocator.release()  # every available pool + malloc_trim, no error
