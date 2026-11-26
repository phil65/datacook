"""Reshape ops: unpivot (melt), pivot table, frequency table (crosstab), transpose.

Results have no index (like every frame here): row labels become columns
(`.reset_index()`), and column labels made from values (pivot, crosstab, transpose) become
text (`.rename(columns=str)`), so later steps can name them.
"""

import ast
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field

from datacook.engine import categories
from datacook.engine.ops import base, series
from datacook.i18n import N_, _


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from datacook.engine.frames import Frame


type Aggregation = Literal[
    "mean", "sum", "count", "min", "max", "median", "first", "last", "std", "var"
]
LABELS_TO_TEXT = ".rename(columns=str)"


class Unpivot(base.CallOp):
    id = "unpivot"
    title = _("Unpivot (melt)")
    description = _(
        "Turn columns into rows: one row per identifier and column, with the column name"
        " and its value (wide to long format)."
    )
    category = categories.RESHAPE
    icon = "mdi.table-arrow-down"
    method = "melt"

    class Params(base.Params):
        id_vars: list[str] = Field(
            [], title=N_("Identifier columns"), json_schema_extra={"widget": "columns"}
        )
        value_vars: list[str] | None = Field(
            None,
            title=N_("Columns to unpivot"),
            description=N_("Empty: all other columns."),
            json_schema_extra={"widget": "columns"},
        )
        var_name: str = Field("variable", title=N_("Name of the column-name column"))
        value_name: str = Field("value", title=N_("Name of the value column"))


class Pivot(base.CallOp):
    """`df.pivot_table(...)`: one value column, one column whose values become columns."""

    id = "pivot"
    title = _("Pivot table")
    description = _(
        "Aggregate a value column per row key and per value of another column (long to wide"
        " format), optionally with totals."
    )
    category = categories.RESHAPE
    icon = "mdi.table-pivot"
    method = "pivot_table"
    then = f".reset_index(){LABELS_TO_TEXT}"

    class Params(base.Params):
        index: list[str] = Field(
            title=N_("Row keys"), min_length=1, json_schema_extra={"widget": "columns"}
        )
        columns: str = Field(
            title=N_("Column with the new column names"), json_schema_extra={"widget": "column"}
        )
        values: str = Field(title=N_("Value column"), json_schema_extra={"widget": "column"})
        aggfunc: Aggregation = Field("mean", title=N_("Function"))
        fill_value: float | None = Field(None, title=N_("Value for empty cells"))
        margins: bool = Field(False, title=N_("Include totals"))
        margins_name: str = Field("All", title=N_("Totals label"))
        dropna: bool = Field(True, title=N_("Drop missing keys"))
        sort: bool = Field(True, title=N_("Sort"))

    @classmethod
    def finish(cls, params: Any, result: Any) -> Any:
        return result.reset_index().rename(columns=str)


class Crosstab(base.Op):
    """`pd.crosstab([df["a"], ...], df["b"])`: counts per combination of values."""

    id = "crosstab"
    title = _("Frequency table")
    description = _(
        "Count the rows per combination of values (cross tabulation), optionally as shares"
        " and with totals."
    )
    category = categories.RESHAPE
    icon = "mdi.table-large"

    class Params(base.Params):
        index: list[str] = Field(
            title=N_("Row keys"), min_length=1, json_schema_extra={"widget": "columns"}
        )
        columns: str = Field(
            title=N_("Column with the new column names"), json_schema_extra={"widget": "column"}
        )
        normalize: Literal["all", "index", "columns"] | None = Field(
            None,
            title=N_("Shares"),
            description=N_("all: of the total; index: per row; columns: per column."),
        )
        margins: bool = Field(False, title=N_("Include totals"))
        margins_name: str = Field("All", title=N_("Totals label"))
        dropna: bool = Field(True, title=N_("Drop missing values"))

    @classmethod
    def _kwargs(cls, params: Params) -> dict[str, Any]:
        return base.call_arguments(params, skip=("index", "columns"))[1]

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        import pandas as pd

        frame = inputs[0]
        index = [frame[c] for c in params.index]
        result = pd.crosstab(index, frame[params.columns], **cls._kwargs(params))
        return result.reset_index().rename(columns=str)

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        var = inputs[0]
        index = f"[{', '.join(series.column_code(var, c) for c in params.index)}]"
        args = [index, series.column_code(var, params.columns)]
        tail = f".reset_index(){LABELS_TO_TEXT}"
        width = len(output) + 3 + len(tail)
        call = base.format_call("pd.crosstab", args, cls._kwargs(params), width)
        return f"{output} = {call}{tail}"

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        call = base.strip_tail(value, f".reset_index(){LABELS_TO_TEXT}")
        if not (
            isinstance(call, ast.Call)
            and base.dotted_name(call.func) == "pd.crosstab"
            and len(call.args) == 2  # noqa: PLR2004
            and isinstance(rows := call.args[0], ast.List)
            and rows.elts
            and isinstance(first := rows.elts[0], ast.Subscript)
            and isinstance(first.value, ast.Name)
            and (var := first.value.id) in bound
        ):
            return None
        index = [c for e in rows.elts if (c := series.column_of(e, var)) is not None]
        columns = series.column_of(call.args[1], var)
        found = base.CallOp.literal_args(call, 2)
        if columns is None or len(index) != len(rows.elts) or found is None or found[0]:
            return None
        params = cls.Params(index=index, columns=columns, **found[1])
        return series.confirm(cls, params, [var], output, stmt)


class Transpose(base.Op):
    """Rows become columns: `df.set_index("name").transpose().reset_index(names="column")`."""

    id = "transpose"
    title = _("Transpose")
    description = _(
        "Swap rows and columns. The column names become a column; the new column names are"
        " the values of a column (or the row numbers)."
    )
    category = categories.RESHAPE
    icon = "mdi.table-sync"

    class Params(base.Params):
        header: str | None = Field(
            None,
            title=N_("Column with the new column names"),
            description=N_("Empty: the row numbers."),
            json_schema_extra={"widget": "column"},
        )
        names: str = Field("column", title=N_("Name of the column-name column"))

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        frame = inputs[0]
        if params.header is not None:
            frame = frame.set_index(params.header)
        return frame.transpose().reset_index(names=params.names).rename(columns=str)

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        source = inputs[0]
        if params.header is not None:
            source = f"{source}.set_index({base.literal(params.header)})"
        reset = f".reset_index(names={base.literal(params.names)})"
        return f"{output} = {source}.transpose(){reset}{LABELS_TO_TEXT}"

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        value = base.strip_tail(value, LABELS_TO_TEXT)
        chain = series.unchain(value) if value is not None else None
        if chain is None:
            return None
        root, links = chain
        if not (isinstance(root, ast.Name) and root.id in bound and len(links) in {2, 3}):
            return None
        try:
            if len(links) == 3:  # noqa: PLR2004
                set_index, *links = links
                if set_index.name != "set_index":
                    return None
                header = set_index.literal_args()[0][0]
            else:
                header = None
            names = links[1].literal_args()[1]["names"]
        except ValueError, IndexError, KeyError:
            return None
        params = cls.Params(header=header, names=names)
        return series.confirm(cls, params, [root.id], output, stmt)
