"""The time column of a step: which column is "the time" (replaces the old DatetimeIndex).

Frames have no meaningful index in the engine: time is an ordinary column. Time series ops
name it in a param marked with the UI hint `TIME_COLUMN` (`{"widget": "column", "role":
"time"}`), so the generated code stays explicit (`df.resample("1min", on="time")`).

Which column that is, is recorded in the steps themselves, not in hidden node metadata, so
it survives project files, recipes and code edits:

1. the nearest step on the path to the node (the node itself first, then its first parents)
   with a time-role param ("Use as time column", "Resample", ...) whose column still exists;
2. else the first column with a date / time dtype.

The app pre-fills time-role fields of a new step with `time_column(session, input_id)`.
"""

from typing import TYPE_CHECKING, Any, Protocol


if TYPE_CHECKING:
    from collections.abc import Sequence

    import pydantic

    from datacook.engine.frames import Column, FrameSummary
    from datacook.engine.node import Node


class NodeSource(Protocol):
    """What `time_column()` needs of a session (`Session`, the app's session protocol)."""

    def get(self, node_id: str) -> Node | None: ...

    def summary(self, node_id: str) -> FrameSummary | None: ...


TIME_COLUMN: dict[str, Any] = {"widget": "column", "role": "time"}
"""`json_schema_extra` of a param holding the time column."""


def time_fields(model: type[pydantic.BaseModel]) -> list[str]:
    """Names of the time-role fields of a params model."""
    return [
        name
        for name, info in model.model_fields.items()
        if isinstance(info.json_schema_extra, dict) and info.json_schema_extra.get("role") == "time"
    ]


def is_datetime(dtype: str) -> bool:
    """Whether a dtype name (`frames.Column.dtype`) is a date / time type."""
    return dtype.startswith(("datetime64", "timestamp"))


def infer(columns: Sequence[Column]) -> str | None:
    """The first date / time column."""
    return next((c.name for c in columns if is_datetime(c.dtype)), None)


def time_column(session: NodeSource, node_id: str) -> str | None:
    """The time column of the node's frame (see the module docstring); None if unknown.

    Uses the node's summary when it was computed (to check the column still exists and to
    infer one); never computes anything.
    """
    summary = session.summary(node_id)
    names = {c.name for c in summary.columns} if summary is not None else None
    current = session.get(node_id)
    while current is not None:
        params = current.record.params
        for field in time_fields(type(params)):
            value = getattr(params, field)
            if isinstance(value, str) and value and (names is None or value in names):
                return value
        current = session.get(current.parents[0]) if current.parents else None
    return infer(summary.columns) if summary is not None else None
