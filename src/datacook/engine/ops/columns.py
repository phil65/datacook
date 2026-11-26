"""Column ops: select, drop, rename, move, sort, change dtypes, copy, combine, calculate."""

import ast
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, Self

import pydantic
from pydantic import Field

from datacook.engine import categories
from datacook.engine.ops import base
from datacook.i18n import N_, _


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from datacook.engine.frames import Frame


class SelectColumns(base.Op):
    id = "select_columns"
    title = _("Select columns")
    description = _("Keep only the given columns, in the given order.")
    category = categories.COLUMNS
    icon = "mdi.table-column-plus-after"

    class Params(base.Params):
        columns: list[str] = Field(
            title=N_("Columns"), min_length=1, json_schema_extra={"widget": "columns"}
        )

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        return inputs[0][params.columns]

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        return f"{output} = {inputs[0]}[{base.literal(params.columns)}]"

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        if not (
            isinstance(value, ast.Subscript)
            and isinstance(value.value, ast.Name)
            and value.value.id in bound
            and isinstance(value.slice, ast.List)
        ):
            return None
        try:
            columns = base.literal_value(value.slice)
        except ValueError:
            return None
        return base.Match(cls.Params(columns=columns), (value.value.id,), output)


class DropColumns(base.CallOp):
    id = "drop_columns"
    title = _("Drop columns")
    description = _("Remove columns.")
    category = categories.COLUMNS
    icon = "mdi.table-column-remove"
    method = "drop"

    class Params(base.Params):
        columns: list[str] = Field(
            title=N_("Columns"), min_length=1, json_schema_extra={"widget": "columns"}
        )


class RenameColumns(base.CallOp):
    id = "rename_columns"
    title = _("Rename columns")
    description = _("Rename columns (old name -> new name).")
    category = categories.COLUMNS
    icon = "mdi.cursor-text"
    method = "rename"

    class Params(base.Params):
        columns: dict[str, str] = Field(
            title=N_("New names"), min_length=1, json_schema_extra={"widget": "column_map"}
        )


class ChangeDtypes(base.CallOp):
    id = "astype"
    title = _("Change data type")
    description = _(
        "Convert columns to other data types (e.g. 'float32', 'int64[pyarrow]', 'category')."
    )
    category = categories.CONVERSION
    icon = "mdi.swap-horizontal"
    method = "astype"
    positional = ("dtype",)

    class Params(base.Params):
        dtype: dict[str, str] = Field(
            title=N_("Data types"), min_length=1, json_schema_extra={"widget": "column_map"}
        )


def _columns_field(title: str = N_("Columns"), min_length: int = 1) -> Any:
    return Field(title=title, min_length=min_length, json_schema_extra={"widget": "columns"})


def _is_frame_columns_drop(node: ast.expr, frame: str) -> ast.expr | None:
    """The argument of `frame.columns.drop(<arg>)`, else None."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "drop"
        and isinstance(attr := node.func.value, ast.Attribute)
        and attr.attr == "columns"
        and isinstance(attr.value, ast.Name)
        and attr.value.id == frame
        and len(node.args) == 1
        and not node.keywords
    ):
        return node.args[0]
    return None


class MoveColumns(base.Op):
    id = "move_columns"
    title = _("Move columns")
    description = _("Move columns to the front or the end; the other columns keep their order.")
    category = categories.COLUMNS
    icon = "mdi.table-column-plus-before"

    class Params(base.Params):
        columns: list[str] = _columns_field()
        position: Literal["first", "last"] = Field("first", title=N_("Position"))

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        frame = inputs[0]
        rest = list(frame.columns.drop(params.columns))
        order = [*params.columns, *rest] if params.position == "first" else [*rest, *params.columns]
        return frame[order]

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        frame = inputs[0]
        moved = ", ".join(base.literal(c) for c in params.columns)
        rest = f"*{frame}.columns.drop({base.literal(params.columns)})"
        order = f"{moved}, {rest}" if params.position == "first" else f"{rest}, {moved}"
        return f"{output} = {frame}[[{order}]]"

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
            and value.value.id in bound
            and isinstance(value.slice, ast.List)
            and len(elts := value.slice.elts) > 1
        ):
            return None
        frame = value.value.id
        first, last = elts[0], elts[-1]
        if isinstance(last, ast.Starred):
            position, starred, named = "first", last, elts[:-1]
        elif isinstance(first, ast.Starred):
            position, starred, named = "last", first, elts[1:]
        else:
            return None
        dropped = _is_frame_columns_drop(starred.value, frame)
        if dropped is None or any(isinstance(e, ast.Starred) for e in named):
            return None
        try:
            columns = [base.literal_value(e) for e in named]
            if base.literal_value(dropped) != columns:
                return None
        except ValueError:
            return None
        params = cls.Params(columns=columns, position=position)
        return base.Match(params, (frame,), output)


class SortColumns(base.CallOp):
    id = "sort_columns"
    title = _("Sort columns")
    description = _("Order the columns by name.")
    category = categories.COLUMNS
    icon = "mdi.sort-alphabetical-ascending"
    method = "sort_index"
    fixed = MappingProxyType({"axis": "columns"})

    class Params(base.Params):
        ascending: bool = Field(True, title=N_("Ascending"))


class AddPrefix(base.CallOp):
    id = "add_prefix"
    title = _("Add prefix")
    description = _("Put a text in front of every column name.")
    category = categories.COLUMNS
    icon = "mdi.format-text-variant"
    method = "add_prefix"
    positional = ("prefix",)

    class Params(base.Params):
        prefix: str = Field(title=N_("Prefix"), min_length=1)


class AddSuffix(base.CallOp):
    id = "add_suffix"
    title = _("Add suffix")
    description = _("Append a text to every column name.")
    category = categories.COLUMNS
    icon = "mdi.format-text-variant-outline"
    method = "add_suffix"
    positional = ("suffix",)

    class Params(base.Params):
        suffix: str = Field(title=N_("Suffix"), min_length=1)


DTYPE_KINDS = ["number", "integer", "floating", "string", "bool", "datetime", "category"]


class SelectDtypes(base.CallOp):
    id = "select_dtypes"
    title = _("Select columns by type")
    description = _(
        "Keep only columns of the given types (e.g. 'number', 'string', 'datetime', 'bool',"
        " 'category') or drop them."
    )
    category = categories.COLUMNS
    icon = "mdi.table-column-plus-after"
    method = "select_dtypes"

    class Params(base.Params):
        include: list[str] | None = Field(None, title=N_("Include types"), examples=[DTYPE_KINDS])
        exclude: list[str] | None = Field(None, title=N_("Exclude types"), examples=[DTYPE_KINDS])

        @pydantic.model_validator(mode="after")
        def _one_given(self) -> Self:
            if not self.include and not self.exclude:
                msg = "include or exclude must name at least one type"
                raise ValueError(msg)
            return self


class ConvertDtypes(base.CallOp):
    id = "convert_dtypes"
    title = _("Infer data types")
    description = _(
        "Convert columns to the best fitting data type (e.g. text columns holding whole"
        " numbers to integers), arrow-backed by default."
    )
    category = categories.CONVERSION
    icon = "mdi.auto-fix"
    method = "convert_dtypes"
    always = ("dtype_backend",)

    class Params(base.Params):
        dtype_backend: Literal["pyarrow", "numpy_nullable"] = Field("pyarrow", title=N_("Backend"))


class Downcast(base.Op):
    id = "downcast"
    title = _("Downcast numbers")
    description = _("Store numeric columns in the smallest data type that holds their values.")
    category = categories.CONVERSION
    icon = "mdi.arrow-collapse-down"

    class Params(base.Params):
        columns: list[str] = _columns_field()
        downcast: Literal["integer", "signed", "unsigned", "float"] = Field(
            "integer", title=N_("Target type")
        )

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        import pandas as pd

        frame = inputs[0]
        part = frame[params.columns].apply(pd.to_numeric, downcast=params.downcast)
        return frame.assign(**part)

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        frame = inputs[0]
        part = f"{frame}[{base.literal(params.columns)}]"
        call = f"{part}.apply(pd.to_numeric, downcast={base.literal(params.downcast)})"
        return f"{output} = {frame}.assign(**{call})"

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        target = base.assign_target(value, bound)
        if target is None:
            return None
        frame, kw = target
        call = kw.value
        if not (
            kw.arg is None
            and isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "apply"
            and isinstance(sub := call.func.value, ast.Subscript)
            and isinstance(sub.value, ast.Name)
            and sub.value.id == frame
            and len(call.args) == 1
            and base.dotted_name(call.args[0]) == "pd.to_numeric"
            and [k.arg for k in call.keywords] == ["downcast"]
        ):
            return None
        try:
            columns = base.literal_value(sub.slice)
            downcast = base.literal_value(call.keywords[0].value)
        except ValueError:
            return None
        return base.Match(cls.Params(columns=columns, downcast=downcast), (frame,), output)


class DuplicateColumns(base.Op):
    id = "duplicate_columns"
    title = _("Duplicate columns")
    description = _("Add copies of columns (name + suffix) at the end.")
    category = categories.COLUMNS
    icon = "mdi.content-copy"

    class Params(base.Params):
        columns: list[str] = _columns_field()
        suffix: str = Field("_copy", title=N_("Suffix"), min_length=1)

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        frame = inputs[0]
        return frame.join(frame[params.columns].add_suffix(params.suffix))

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        frame = inputs[0]
        part = f"{frame}[{base.literal(params.columns)}].add_suffix({base.literal(params.suffix)})"
        return f"{output} = {frame}.join({part})"

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        if not (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "join"
            and isinstance(value.func.value, ast.Name)
            and (frame := value.func.value.id) in bound
            and len(value.args) == 1
            and not value.keywords
            and isinstance(call := value.args[0], ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "add_suffix"
            and isinstance(sub := call.func.value, ast.Subscript)
            and isinstance(sub.value, ast.Name)
            and sub.value.id == frame
            and len(call.args) == 1
            and not call.keywords
        ):
            return None
        try:
            columns = base.literal_value(sub.slice)
            suffix = base.literal_value(call.args[0])
        except ValueError:
            return None
        return base.Match(cls.Params(columns=columns, suffix=suffix), (frame,), output)


STRING_DTYPE = "string"
"""pandas 3 default string dtype (arrow-backed, missing = NA)."""


class CombineColumns(base.Op):
    id = "combine_columns"
    title = _("Combine columns")
    description = _("Join the values of several columns as text into a new column.")
    category = categories.COLUMNS
    icon = "mdi.table-merge-cells"

    class Params(base.Params):
        columns: list[str] = _columns_field(min_length=2)
        name: str = Field(title=N_("New column"), min_length=1)
        sep: str = Field(" ", title=N_("Separator"))
        na_rep: str | None = Field("", title=N_("Missing values as (empty: result missing)"))

    @classmethod
    def _cat_kwargs(cls, params: Params) -> dict[str, Any]:
        return {"sep": params.sep, "na_rep": params.na_rep}

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        frame = inputs[0]
        first, *rest = params.columns
        joined = (
            frame[first]
            .astype(STRING_DTYPE)
            .str.cat(frame[rest].astype(STRING_DTYPE), **cls._cat_kwargs(params))
        )
        return frame.assign(**{params.name: joined})

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        frame = inputs[0]
        first, *rest = params.columns
        dtype = base.literal(STRING_DTYPE)
        func = f"{frame}[{base.literal(first)}].astype({dtype}).str.cat"
        others = f"{frame}[{base.literal(rest)}].astype({dtype})"
        prefix = f"{output} = {frame}.assign({base.assign_kwarg(params.name, '')}"
        call = base.format_call(func, [others], cls._cat_kwargs(params), len(prefix) + 1)
        return f"{output} = {frame}.assign({base.assign_kwarg(params.name, call)})"

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:  # noqa: PLR0911
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        target = base.assign_target(value, bound)
        if target is None:
            return None
        frame, kw = target
        found = base.assign_item(kw)
        if found is None:
            return None
        name, call = found

        def astype_of(node: ast.expr) -> Any:
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "astype"
                and len(node.args) == 1
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == STRING_DTYPE
                and isinstance(sub := node.func.value, ast.Subscript)
                and isinstance(sub.value, ast.Name)
                and sub.value.id == frame
            ):
                return None
            return base.literal_value(sub.slice)

        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "cat"
            and isinstance(acc := call.func.value, ast.Attribute)
            and acc.attr == "str"
            and len(call.args) == 1
        ):
            return None
        try:
            first = astype_of(acc.value)
            rest = astype_of(call.args[0])
            kwargs = {k.arg: base.literal_value(k.value) for k in call.keywords if k.arg}
        except ValueError:
            return None
        if not isinstance(first, str) or not isinstance(rest, list):
            return None
        params = cls.Params(columns=[first, *rest], name=name, **kwargs)
        return base.Match(params, (frame,), output)


class CalculateColumns(base.CallOp):
    id = "calculate_columns"
    title = _("Calculate columns")
    description = _(
        "Add or overwrite columns with formulas, one per line, e.g. 'total = price * amount'"
        " (pandas eval syntax)."
    )
    category = categories.COLUMNS
    icon = "mdi.calculator-variant-outline"
    method = "eval"
    positional = ("expr",)

    class Params(base.Params):
        expr: str = Field(title=N_("Formulas"), min_length=1, examples=["total = price * amount"])

        @pydantic.field_validator("expr")
        @classmethod
        def _is_assignment(cls, value: str) -> str:
            if "=" not in value:
                msg = "each line must assign a column: 'name = expression'"
                raise ValueError(msg)
            return value
