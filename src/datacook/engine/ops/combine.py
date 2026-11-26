"""Ops combining frames or rows: merge (two inputs), group-by aggregate."""

import ast
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field

from datacook.engine import categories
from datacook.engine.ops import base
from datacook.i18n import N_, _


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from datacook.engine.frames import Frame


class Merge(base.CallOp):
    id = "merge"
    title = _("Merge")
    description = _("Join two tables on key columns (database-style join).")
    category = categories.COMBINE
    icon = "mdi.set-merge"
    n_inputs = 2
    method = "merge"

    class Params(base.Params):
        how: Literal["inner", "left", "right", "outer", "cross"] = Field(
            "inner", title=N_("Join type")
        )
        on: list[str] | None = Field(
            None, title=N_("Key columns"), json_schema_extra={"widget": "columns"}
        )
        left_on: list[str] | None = Field(
            None, title=N_("Left key columns"), json_schema_extra={"widget": "columns"}
        )
        right_on: list[str] | None = Field(
            None,
            title=N_("Right key columns"),
            json_schema_extra={"widget": "columns", "input": 1},
        )
        suffixes: tuple[str, str] = Field(("_x", "_y"), title=N_("Suffixes"))
        indicator: bool = Field(False, title=N_("Add indicator column"))


class Aggregation(base.Params):
    column: str = Field(title=N_("Column"), json_schema_extra={"widget": "column"})
    func: str = Field("sum", title=N_("Function"), examples=["sum", "mean", "count", "max"])
    name: str | None = Field(None, title=N_("Result name"))

    @property
    def output_name(self) -> str:
        return self.name or f"{self.column}_{self.func}"


class GroupByAggregate(base.Op):
    id = "groupby_aggregate"
    title = _("Group and aggregate")
    description = _("Group rows by key columns and aggregate other columns per group.")
    category = categories.RESHAPE
    icon = "mdi.group"

    class Params(base.Params):
        by: list[str] = Field(
            title=N_("Group by"), min_length=1, json_schema_extra={"widget": "columns"}
        )
        aggregations: list[Aggregation] = Field(title=N_("Aggregations"), min_length=1)
        dropna: bool = Field(True, title=N_("Drop missing keys"))
        sort: bool = Field(True, title=N_("Sort groups"))

    @classmethod
    def _named(cls, params: Params) -> dict[str, tuple[str, str]]:
        return {a.output_name: (a.column, a.func) for a in params.aggregations}

    @classmethod
    def _groupby_kwargs(cls, params: Params) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"as_index": False}
        if not params.dropna:
            kwargs["dropna"] = False
        if not params.sort:
            kwargs["sort"] = False
        return kwargs

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        grouped = inputs[0].groupby(params.by, **cls._groupby_kwargs(params))
        return grouped.agg(**cls._named(params))

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        gb = base.format_call(
            f"{inputs[0]}.groupby", [base.literal(params.by)], cls._groupby_kwargs(params)
        )
        named = cls._named(params)
        if all(name.isidentifier() for name in named):
            agg = base.format_call(".agg", [], named, len(output) + len(gb) + 3)
        else:
            agg = f".agg(**{base.literal(named)})"
        return f"{output} = {gb}{agg}"

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        if not (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "agg"
            and not value.args
        ):
            return None
        gb = value.func.value
        if not (
            isinstance(gb, ast.Call)
            and isinstance(gb.func, ast.Attribute)
            and gb.func.attr == "groupby"
            and isinstance(gb.func.value, ast.Name)
            and gb.func.value.id in bound
            and len(gb.args) == 1
        ):
            return None
        try:
            by = base.literal_value(gb.args[0])
            gb_kwargs = {kw.arg: base.literal_value(kw.value) for kw in gb.keywords}
            named: dict[str, Any] = {}
            for kw in value.keywords:
                if kw.arg is None:
                    named.update(base.literal_value(kw.value))
                else:
                    named[kw.arg] = base.literal_value(kw.value)
        except ValueError:
            return None
        if gb_kwargs.pop("as_index", True) is not False or set(gb_kwargs) - {"dropna", "sort"}:
            return None
        aggregations = []
        for name, spec in named.items():
            column, func = spec
            default = f"{column}_{func}"
            aggregations.append(
                Aggregation(column=column, func=func, name=None if name == default else name)
            )
        params = cls.Params(
            by=[by] if isinstance(by, str) else by,
            aggregations=aggregations,
            dropna=gb_kwargs.get("dropna", True),
            sort=gb_kwargs.get("sort", True),
        )
        return base.Match(params, (gb.func.value.id,), output)
