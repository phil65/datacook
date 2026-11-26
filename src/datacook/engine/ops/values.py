"""Value ops on all or some columns: absolute values, clip, replace."""

import ast
import math
from typing import TYPE_CHECKING, Any

import pydantic
from pydantic import Field

from datacook.engine import categories
from datacook.engine.ops import base
from datacook.i18n import N_, _


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from datacook.engine.frames import Frame


type Scalar = bool | int | float | str


class Abs(base.ColumnsCallOp):
    id = "abs"
    title = _("Absolute values")
    description = _("Replace numbers by their absolute value.")
    category = categories.GENERAL
    icon = "mdi.plus-minus-variant"
    method = "abs"

    class Params(base.Params):
        columns: list[str] = Field(
            title=N_("Columns"), min_length=1, json_schema_extra={"widget": "columns"}
        )


class Clip(base.ColumnsCallOp):
    id = "clip"
    title = _("Clip values")
    description = _(
        "Limit numbers to a range: values below the lower bound become the lower bound,"
        " values above the upper bound become the upper bound."
    )
    category = categories.GENERAL
    icon = "mdi.arrow-collapse-vertical"
    method = "clip"

    class Params(base.Params):
        columns: list[str] = Field(
            title=N_("Columns"), min_length=1, json_schema_extra={"widget": "columns"}
        )
        lower: float | None = Field(None, title=N_("Lower bound"))
        upper: float | None = Field(None, title=N_("Upper bound"))


def _no_nan(values: list[Scalar]) -> list[Scalar]:
    if any(isinstance(v, float) and math.isnan(v) for v in values):
        msg = "NaN is not a value to replace: use 'NaN to missing'"
        raise ValueError(msg)
    return values


class ReplaceValues(base.Op):
    """`df.replace(old, new)`; new = None replaces with a missing value (`pd.NA`).

    `pd.NA` keeps arrow dtypes (replacing with `None` would turn columns into `object`).
    """

    id = "replace_values"
    title = _("Replace values")
    description = _(
        "Replace values (in all or some columns) by a new value, or mark them as missing."
    )
    category = categories.GENERAL
    icon = "mdi.find-replace"

    class Params(base.Params):
        to_replace: list[Scalar] = Field(title=N_("Values"), min_length=1)
        value: Scalar | None = Field(None, title=N_("New value (empty: missing)"))
        columns: list[str] | None = Field(
            None, title=N_("Columns"), json_schema_extra={"widget": "columns"}
        )

        _check_nan = pydantic.field_validator("to_replace")(_no_nan)

    @classmethod
    def _call(cls, params: Params) -> tuple[Any, Any]:
        old: Any = params.to_replace[0] if len(params.to_replace) == 1 else params.to_replace
        if params.columns is not None:
            old = dict.fromkeys(params.columns, old)
        return old, params.value

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        import pandas as pd

        old, new = cls._call(params)
        return inputs[0].replace(old, pd.NA if new is None else new)

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        old, new = cls._call(params)
        new_code = "pd.NA" if new is None else base.literal(new)
        call = base.format_call(f"{inputs[0]}.replace", [base.literal(old), new_code], {})
        return f"{output} = {call}"

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        if not (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "replace"
            and isinstance(value.func.value, ast.Name)
            and (frame := value.func.value.id) in bound
            and len(value.args) == 2  # noqa: PLR2004
            and not value.keywords
        ):
            return None
        old_node, new_node = value.args
        try:
            old = base.literal_value(old_node)
            new = None if base.dotted_name(new_node) == "pd.NA" else base.literal_value(new_node)
        except ValueError:
            return None
        columns = None
        if isinstance(old, dict):
            columns = list(old)
            olds = list(old.values())
            if not olds or any(o != olds[0] for o in olds):
                return None  # different values per column: not this op
            old = olds[0]
        to_replace = old if isinstance(old, list) else [old]
        params = cls.Params(to_replace=to_replace, value=new, columns=columns)
        return base.Match(params, (frame,), output)
