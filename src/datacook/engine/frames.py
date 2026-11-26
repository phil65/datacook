"""The narrow engine interface to the dataframe library.

Everything outside `ops/` and `formats` that needs to look at a frame goes through these
functions, so the dataframe library can be swapped per op later.

Today the only backend is pandas 3 (copy-on-write, pyarrow-backed dtypes). An op declares
its backend (`Op.backend`); `ensure_backend()` is the conversion point when a second one
(polars) arrives.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import pandas as pd


if TYPE_CHECKING:
    from collections.abc import Sequence

type Frame = pd.DataFrame
type Backend = Literal["pandas"]


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    dtype: str


@dataclass(frozen=True, slots=True)
class FrameSummary:
    """What views need without holding a frame: shape, schema, memory."""

    n_rows: int
    columns: tuple[Column, ...]
    nbytes: int

    @property
    def n_columns(self) -> int:
        return len(self.columns)


def is_frame(obj: Any) -> bool:
    return isinstance(obj, pd.DataFrame)


def ensure_backend(frame: Frame, backend: Backend) -> Frame:
    """Convert `frame` to the frame type of `backend` (identity while pandas is the only one)."""
    if backend != "pandas":
        msg = f"Unsupported backend {backend!r}"
        raise ValueError(msg)
    return frame


def to_arrow_dtypes(frame: Frame) -> Frame:
    """Convert numpy / object columns to pyarrow-backed dtypes (no-op for arrow columns)."""
    if all(isinstance(dt, pd.ArrowDtype) for dt in frame.dtypes):
        return frame
    return frame.convert_dtypes(dtype_backend="pyarrow")


def summary(frame: Frame, buffers_: dict[int, int] | None = None) -> FrameSummary:
    """Shape, schema and size; pass `buffers(frame)` if already measured."""
    cols = tuple(Column(str(name), str(dtype)) for name, dtype in frame.dtypes.items())
    size = nbytes(frame) if buffers_ is None else int(sum(buffers_.values()))
    return FrameSummary(n_rows=len(frame), columns=cols, nbytes=size)


def window(
    frame: Frame,
    start: int,
    stop: int,
    columns: Sequence[str] | None = None,
) -> Frame:
    """Rows `start:stop` (and optionally a column subset); a view under copy-on-write."""
    part = frame.iloc[start:stop]
    return part if columns is None else part[list(columns)]


def nbytes(frame: Frame) -> int:
    """Size of the frame's data (strings counted deep)."""
    return int(sum(buffers(frame).values()))


def buffers(frame: Frame) -> dict[int, int]:
    """Memory buffers of a frame, `{key: nbytes}`.

    Frames that share data (copy-on-write: rename, column subset, ...) return the same keys
    for the shared buffers, so a cache can count shared memory once.
    """
    result: dict[int, int] = {}
    for i in range(frame.shape[1]):
        col = frame.iloc[:, i]
        arr = col.array
        pa_array = getattr(arr, "_pa_array", None)  # ArrowExtensionArray, ArrowStringArray
        if pa_array is not None:
            for chunk in pa_array.chunks:
                for buf in chunk.buffers():
                    if buf is not None:
                        result[buf.address] = buf.size
            continue
        np_arr = getattr(arr, "_ndarray", None)
        if np_arr is not None and np_arr.size:
            address = np_arr.__array_interface__["data"][0]
            deep = np_arr.dtype == object
            result[address] = (
                int(col.memory_usage(index=False, deep=True)) if deep else np_arr.nbytes
            )
            continue
        # categoricals, masked arrays, empty columns: no stable address, count as unshared
        result[-(i + 1) - (id(frame) << 16)] = int(col.memory_usage(index=False, deep=True))
    return result
