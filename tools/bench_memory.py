"""Memory benchmark: the engine vs raw pandas (DATACOOK_PLAN.md section 1 / appendix).

2M rows x 10 mixed columns, a chain of 8 typical steps, every intermediate kept.

usage: python tools/bench_memory.py <mode> [rows]
modes:
  pandas_keep    raw pandas, pyarrow dtypes (read_parquet dtype_backend="pyarrow"), keep all
  pandas_np_keep raw pandas, default dtypes (numpy + pyarrow-backed `str`), keep all
  engine_keep    datacook.engine Session, unlimited budget (all 9 frames cached)
  engine_budget  datacook.engine Session, budget = 2x source frame (LRU eviction)
RSS after gc + malloc_trim(0); "peak" = VmHWM during the step (reset per step); "arrow pool" =
bytes allocated by pyarrow. Run with `ARROW_DEFAULT_MEMORY_POOL=system` so that freed arrow
memory goes back to the OS (with the default jemalloc/mimalloc pool, RSS includes retained
allocator memory).
"""

import ctypes
import gc
import pathlib
import sys
import tempfile
import time

import numpy as np
import pandas as pd
import pyarrow as pa


MODE = sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 2_000_000  # noqa: PLR2004
NUM = ["f0", "f1", "f2", "f3"]
libc = ctypes.CDLL("libc.so.6")
rows: list[tuple[str, float, float, float, str]] = []


def rss() -> dict[str, float]:
    result = {}
    for line in pathlib.Path("/proc/self/status").read_text().splitlines():
        key, value = line.split(":", 1)
        if key in ("VmRSS", "VmHWM"):
            result[key] = int(value.split()[0]) / 1024
    return result


def reset_peak() -> None:
    pathlib.Path("/proc/self/clear_refs").write_text("5")


def mark(label: str, t0: float, extra: str = "") -> None:
    gc.collect()
    libc.malloc_trim(0)
    r = rss()
    extra = f"arrow pool {pa.total_allocated_bytes() / 2**20:5.0f} MB  {extra}"
    rows.append((label, r["VmRSS"], r["VmHWM"], time.perf_counter() - t0, extra))
    reset_peak()


def make_data() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(0)
    f = {f"f{i}": rng.normal(size=N) for i in range(4)}
    for v in f.values():
        v[rng.random(N) < 0.05] = np.nan  # noqa: PLR2004
    words = np.array([f"cat_{i}" for i in range(20)])
    return dict(
        **f,
        i0=rng.integers(0, 1000, N),
        i1=rng.integers(0, 10**9, N),
        ts=np.datetime64("2024-01-01T00:00:00.000")
        + rng.integers(0, 10**8, N).astype("timedelta64[ms]"),
        s_low=words[rng.integers(0, 20, N)],
        s_high=np.char.add("id_", rng.integers(0, 10**9, N).astype(str)),
        flag=rng.random(N) < 0.5,  # noqa: PLR2004
    )


def main() -> None:
    tmp = pathlib.Path(tempfile.mkdtemp())
    path = tmp / "data.parquet"
    pd.DataFrame(make_data()).to_parquet(path)
    gc.collect()
    libc.malloc_trim(0)
    base = rss()["VmRSS"]
    reset_peak()
    t0 = time.perf_counter()

    if MODE.startswith("pandas"):
        backend = {"dtype_backend": "pyarrow"} if MODE == "pandas_keep" else {}
        df = pd.read_parquet(path, **backend)
        mark("load", t0, f"{df.memory_usage(deep=True).sum() / 2**20:.0f} MB deep")
        astype = "float32[pyarrow]" if MODE == "pandas_keep" else "float32"
        steps = [
            ("sort_values", lambda d: d.sort_values(by=["f0"], ascending=False)),
            ("ffill", lambda d: d.ffill()),
            ("str.upper", lambda d: d.assign(s_low=d["s_low"].str.upper())),
            ("diff(num cols)", lambda d: d.assign(**d[NUM].diff())),
            ("rename", lambda d: d.rename(columns={"f0": "x0"})),
            ("astype i0", lambda d: d.astype({"i0": astype})),
            ("drop_duplicates", lambda d: d.drop_duplicates(subset=["s_high"])),
            ("query", lambda d: d.query("x0 > 0")),
        ]
        keep = [df]
        for label, fn in steps:
            t = time.perf_counter()
            df = fn(df)
            keep.append(df)
            mark(label, t)
    else:
        from datacook.engine import Session
        from datacook.engine.ops import code, columns, missing, rows as row_ops, sources

        session = Session(memory_budget=2**40)
        src = session.add(sources.ReadParquet.record(path=str(path)))
        frame = session.materialize(src.id)
        size = session.memory().used
        mark("load", t0, f"{size / 2**20:.0f} MB")
        del frame
        if MODE == "engine_budget":
            session.set_memory_budget(2 * size)
        records = [
            ("sort_values", row_ops.SortRows.record(by=["f0"], ascending=False)),
            ("ffill", missing.FillForward.record()),
            ("str.upper", code.CustomCode.record(code='df["s_low"] = df["s_low"].str.upper()')),
            ("diff(num cols)", code.CustomCode.record(code=f"df = df.assign(**df[{NUM}].diff())")),
            ("rename", columns.RenameColumns.record(columns={"f0": "x0"})),
            ("astype i0", columns.ChangeDtypes.record(dtype={"i0": "float32[pyarrow]"})),
            ("drop_duplicates", row_ops.DropDuplicates.record(subset=["s_high"])),
            ("query", row_ops.FilterRows.record(expr="x0 > 0")),
        ]
        node = src
        for label, record in records:
            t = time.perf_counter()
            node = session.add(record, [node])
            session.materialize(node.id)
            mem = session.memory()
            mark(label, t, f"cache {mem.used / 2**20:.0f} MB, {mem.cached_nodes} frames")
        print(session.code([node.id]))

    print(f"mode={MODE} N={N} baseline RSS={base:.0f} MB")
    print(f"{'step':18s} {'RSS':>7s} {'held':>7s} {'peak':>7s} {'secs':>6s}")
    for label, r, p, s, extra in rows:
        print(f"{label:18s} {r:7.0f} {r - base:7.0f} {p:7.0f} {s:6.2f}  {extra}")


if __name__ == "__main__":
    main()
