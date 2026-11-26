"""Row ops: filter, sort, head / tail, slice, top-k, sample, drop duplicates, reset index."""

import ast
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field

from datacook.engine import categories
from datacook.engine.ops import base
from datacook.i18n import N_, _


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from datacook.engine.frames import Frame


class FilterRows(base.CallOp):
    id = "filter_rows"
    title = _("Filter rows")
    description = _("Keep the rows for which an expression is true (pandas query syntax).")
    category = categories.FILTER
    icon = "mdi.filter-outline"
    method = "query"
    positional = ("expr",)

    class Params(base.Params):
        expr: str = Field(title=N_("Expression"), min_length=1, examples=["a > 0 and b == 'x'"])


class SortRows(base.CallOp):
    id = "sort_rows"
    title = _("Sort rows")
    description = _("Sort rows by one or more columns.")
    category = categories.ROWS
    icon = "mdi.sort"
    method = "sort_values"

    class Params(base.Params):
        by: list[str] = Field(
            title=N_("Columns"), min_length=1, json_schema_extra={"widget": "columns"}
        )
        ascending: bool | list[bool] = Field(True, title=N_("Ascending"))
        na_position: Literal["first", "last"] = Field("last", title=N_("Missing values"))
        kind: Literal["quicksort", "mergesort", "heapsort", "stable"] = Field(
            "quicksort", title=N_("Algorithm")
        )
        ignore_index: bool = Field(False, title=N_("Reset index"))


class Head(base.CallOp):
    id = "head"
    title = _("First rows")
    description = _("Keep the first n rows.")
    category = categories.ROWS
    icon = "mdi.format-vertical-align-top"
    method = "head"
    positional = ("n",)

    class Params(base.Params):
        n: int = Field(5, title=N_("Rows"))


class Sample(base.CallOp):
    id = "sample"
    title = _("Random sample")
    description = _(
        "Random rows (a fixed seed keeps the result stable when the node is recomputed)."
    )
    category = categories.ROWS
    icon = "mdi.dice-multiple-outline"
    method = "sample"

    class Params(base.Params):
        n: int | None = Field(None, title=N_("Rows"), ge=0)
        frac: float | None = Field(None, title=N_("Fraction"), ge=0)
        replace: bool = Field(False, title=N_("With replacement"))
        random_state: int = Field(0, title=N_("Seed"))


class DropDuplicates(base.CallOp):
    id = "drop_duplicates"
    title = _("Drop duplicates")
    description = _("Remove duplicate rows (optionally compared on a subset of columns).")
    category = categories.ROWS
    icon = "mdi.content-duplicate"
    method = "drop_duplicates"

    class Params(base.Params):
        subset: list[str] | None = Field(
            None, title=N_("Columns"), json_schema_extra={"widget": "columns"}
        )
        keep: Literal["first", "last", False] = Field("first", title=N_("Keep"))
        ignore_index: bool = Field(False, title=N_("Reset index"))


class Tail(Head):
    id = "tail"
    title = _("Last rows")
    description = _("Keep the last n rows.")
    icon = "mdi.format-vertical-align-bottom"
    method = "tail"


class NLargest(base.CallOp):
    id = "nlargest"
    title = _("Largest values")
    description = _("Keep the n rows with the largest values in the given columns.")
    category = categories.FILTER
    icon = "mdi.sort-numeric-descending"
    method = "nlargest"
    positional = ("n",)

    class Params(base.Params):
        n: int = Field(5, title=N_("Rows"), ge=0)
        columns: list[str] = Field(
            title=N_("Columns"), min_length=1, json_schema_extra={"widget": "columns"}
        )
        keep: Literal["first", "last", "all"] = Field("first", title=N_("Ties"))


class NSmallest(NLargest):
    id = "nsmallest"
    title = _("Smallest values")
    description = _("Keep the n rows with the smallest values in the given columns.")
    icon = "mdi.sort-numeric-ascending"
    method = "nsmallest"


class SliceRows(base.Op):
    id = "slice_rows"
    title = _("Slice rows")
    description = _(
        "Keep rows by position: from start (inclusive) to stop (exclusive), every n-th row."
    )
    category = categories.ROWS
    icon = "mdi.table-split-cell"

    class Params(base.Params):
        start: int | None = Field(None, title=N_("Start"))
        stop: int | None = Field(None, title=N_("Stop"))
        step: int | None = Field(None, title=N_("Every n-th row"), ge=1)

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        return inputs[0].iloc[params.start : params.stop : params.step]

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        start, stop = ("" if v is None else str(v) for v in (params.start, params.stop))
        index = f"{start}:{stop}" if params.step is None else f"{start}:{stop}:{params.step}"
        return f"{output} = {inputs[0]}.iloc[{index}]"

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        if not (
            isinstance(value, ast.Subscript)
            and isinstance(value.value, ast.Attribute)
            and value.value.attr == "iloc"
            and isinstance(value.value.value, ast.Name)
            and (frame := value.value.value.id) in bound
            and isinstance(index := value.slice, ast.Slice)
        ):
            return None
        try:
            start, stop, step = (
                None if node is None else base.literal_value(node)
                for node in (index.lower, index.upper, index.step)
            )
        except ValueError:
            return None
        return base.Match(cls.Params(start=start, stop=stop, step=step), (frame,), output)


type Scalar = bool | int | float | str


class FilterIsIn(base.Op):
    id = "filter_isin"
    title = _("Filter by values")
    description = _("Keep the rows whose value in a column is one of the given values.")
    category = categories.FILTER
    icon = "mdi.filter-variant-plus"

    class Params(base.Params):
        column: str = Field(title=N_("Column"), json_schema_extra={"widget": "column"})
        values: list[Scalar] = Field(title=N_("Values"), min_length=1)
        invert: bool = Field(False, title=N_("Keep the other rows"))

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        frame = inputs[0]
        mask = frame[params.column].isin(params.values)
        return frame[~mask if params.invert else mask]

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        frame = inputs[0]
        mask = f"{frame}[{base.literal(params.column)}].isin({base.literal(params.values)})"
        return f"{output} = {frame}[{'~' if params.invert else ''}{mask}]"

    @classmethod
    def from_code(  # noqa: PLR0911
        cls, stmt: ast.stmt, bound: Mapping[str, Any]
    ) -> base.Match | None:
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        if not (
            isinstance(value, ast.Subscript)
            and isinstance(value.value, ast.Name)
            and (frame := value.value.id) in bound
        ):
            return None
        mask = value.slice
        invert = isinstance(mask, ast.UnaryOp) and isinstance(mask.op, ast.Invert)
        if isinstance(mask, ast.UnaryOp):
            if not invert:
                return None
            mask = mask.operand
        if not (
            isinstance(mask, ast.Call)
            and isinstance(mask.func, ast.Attribute)
            and mask.func.attr == "isin"
            and isinstance(sub := mask.func.value, ast.Subscript)
            and isinstance(sub.value, ast.Name)
            and sub.value.id == frame
            and len(mask.args) == 1
            and not mask.keywords
        ):
            return None
        try:
            column = base.literal_value(sub.slice)
            values = base.literal_value(mask.args[0])
        except ValueError:
            return None
        if not isinstance(column, str):
            return None
        params = cls.Params(column=column, values=values, invert=invert)
        return base.Match(params, (frame,), output)


class ResetIndex(base.CallOp):
    id = "reset_index"
    title = _("Reset index")
    description = _("Number the rows 0, 1, 2, ...; the old index becomes columns or is dropped.")
    category = categories.ROWS
    icon = "mdi.format-list-numbered"
    method = "reset_index"

    class Params(base.Params):
        drop: bool = Field(False, title=N_("Drop the old index"))
