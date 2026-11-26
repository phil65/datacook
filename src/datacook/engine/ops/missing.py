"""Missing value ops.

**Missing values (policy).** Tables use arrow-backed dtypes, where a missing value is a
*null* (`pd.NA`): readers produce nulls, `isna()` / `fillna()` / `dropna()` and every op
here work on nulls. A float `NaN` ("not a number", e.g. from a numpy computation or a
Parquet file written that way) is a *value* in an arrow float column, not a missing one:
"NaN to missing" turns NaNs into nulls. In numpy float columns (after a cast to `"float64"`)
pandas treats NaN as missing, so the ops behave the same there. Ops that write missing
values write `pd.NA`, which keeps the column dtype (`None` would make it `object`).
"""

import ast
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field

from datacook.engine import categories
from datacook.engine.ops import base, series
from datacook.i18n import N_, _


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from datacook.engine.frames import Frame


type Scalar = bool | int | float | str


def _subset() -> Any:
    return Field(None, title=N_("Columns (empty: all)"), json_schema_extra={"widget": "columns"})


def _columns() -> Any:
    return Field(title=N_("Columns"), min_length=1, json_schema_extra={"widget": "columns"})


class FillMissing(base.CallOp):
    id = "fill_missing"
    title = _("Fill missing values")
    description = _("Replace missing values with a value (or one value per column).")
    category = categories.NAN
    icon = "mdi.format-color-fill"
    method = "fillna"
    positional = ("value",)

    class Params(base.Params):
        value: Scalar | dict[str, Scalar] = Field(title=N_("Value"))


class FillForward(series.SeriesOp):
    id = "ffill"
    title = _("Fill forward")
    description = _("Fill missing values with the last valid value.")
    category = categories.NAN
    icon = "mdi.arrow-down-bold"
    method = "ffill"
    frame_call = True

    class Params(base.Params):
        limit: int | None = Field(None, title=N_("Limit"), ge=1)
        columns: list[str] | None = _subset()


class FillBackward(FillForward):
    id = "bfill"
    title = _("Fill backward")
    description = _("Fill missing values with the next valid value.")
    icon = "mdi.arrow-up-bold"
    method = "bfill"


STATISTICS = ("mean", "median", "min", "max", "mode")


class FillWithStatistic(base.Op):
    """`df.fillna(df[cols].mean())` (one fill value per column).

    The mode is `df[cols].mode().head(1).squeeze(axis=0)`: the first mode per column, and
    no error on an empty table (`.iloc[0]` would raise).
    """

    id = "fill_statistic"
    title = _("Fill with mean / median / mode")
    description = _(
        "Fill missing values of each column with a statistic of that column"
        " (mean, median, minimum, maximum or most frequent value)."
    )
    category = categories.NAN
    icon = "mdi.format-color-fill"

    class Params(base.Params):
        columns: list[str] = _columns()
        statistic: Literal["mean", "median", "min", "max", "mode"] = Field(
            "mean", title=N_("Statistic")
        )

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        frame = inputs[0]
        part = frame[params.columns]
        if params.statistic == "mode":
            fill = part.mode().head(1).squeeze(axis=0)
        else:
            fill = getattr(part, params.statistic)()
        return frame.fillna(fill)

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        frame = inputs[0]
        part = f"{frame}[{base.literal(params.columns)}]"
        if params.statistic == "mode":
            fill = f"{part}.mode().head(1).squeeze(axis=0)"
        else:
            fill = f"{part}.{params.statistic}()"
        return f"{output} = {frame}.fillna({fill})"

    @classmethod
    def from_code(  # noqa: PLR0911
        cls, stmt: ast.stmt, bound: Mapping[str, Any]
    ) -> base.Match | None:
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        if not (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "fillna"
            and isinstance(value.func.value, ast.Name)
            and (frame := value.func.value.id) in bound
            and len(value.args) == 1
            and not value.keywords
            and isinstance(fill := value.args[0], ast.Call)
        ):
            return None
        text = ast.unparse(fill)
        prefix = f"{frame}["
        if not text.startswith(prefix):
            return None
        index_end = text.find("].", len(prefix))
        if index_end < 0:
            return None
        try:
            columns = ast.literal_eval(text[len(prefix) : index_end])
        except ValueError, SyntaxError:
            return None
        rest = text[index_end + 2 :]
        statistic = {f"{s}()": s for s in STATISTICS if s != "mode"}.get(rest)
        if rest == "mode().head(1).squeeze(axis=0)":
            statistic = "mode"
        if statistic is None or not isinstance(columns, list):
            return None
        params = cls.Params.model_validate({"columns": columns, "statistic": statistic})
        return base.Match(params, (frame,), output)


class Interpolate(series.SeriesOp):
    id = "interpolate"
    title = _("Interpolate missing values")
    description = _(
        "Fill missing numbers linearly between the neighbouring valid values"
        " (integer columns become floats)."
    )
    category = categories.NAN
    icon = "mdi.chart-bell-curve-cumulative"
    method = "interpolate"
    frame_call = True

    class Params(base.Params):
        columns: list[str] = _columns()
        limit: int | None = Field(None, title=N_("Limit"), ge=1)
        limit_direction: Literal["forward", "backward", "both"] = Field(
            "forward", title=N_("Direction")
        )
        limit_area: Literal["inside", "outside"] | None = Field(None, title=N_("Area"))


class DropMissing(base.CallOp):
    id = "drop_missing"
    title = _("Drop rows with missing values")
    description = _("Remove rows that contain missing values.")
    category = categories.NAN
    icon = "mdi.table-row-remove"
    method = "dropna"

    class Params(base.Params):
        how: Literal["any", "all"] = Field("any", title=N_("Drop if"))
        subset: list[str] | None = Field(
            None, title=N_("Columns"), json_schema_extra={"widget": "columns"}
        )
        ignore_index: bool = Field(False, title=N_("Reset index"))


class DropMissingColumns(base.CallOp):
    id = "drop_missing_columns"
    title = _("Drop columns with missing values")
    description = _("Remove columns that contain missing values (any or only missing values).")
    category = categories.NAN
    icon = "mdi.table-column-remove"
    method = "dropna"
    fixed = MappingProxyType({"axis": "columns"})

    class Params(base.Params):
        how: Literal["any", "all"] = Field("all", title=N_("Drop if"))


class IsMissing(base.CallOp):
    id = "isna"
    title = _("Missing value mask")
    description = _("Replace every value with True if it is missing, else False.")
    category = categories.NAN
    icon = "mdi.checkbox-blank-off-outline"
    method = "isna"


def _any_missing(params: Any, frame: str) -> str:
    part = frame if params.columns is None else f"{frame}[{base.literal(params.columns)}]"
    return f"{part}.isna().{params.how}(axis=1)"


class FilterMissing(base.Op):
    id = "filter_missing"
    title = _("Rows with missing values")
    description = _("Keep only the rows that have missing values (to inspect them).")
    category = categories.NAN
    icon = "mdi.filter-variant-remove"

    class Params(base.Params):
        how: Literal["any", "all"] = Field("any", title=N_("Keep if"))
        columns: list[str] | None = _subset()

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        frame = inputs[0]
        part = frame if params.columns is None else frame[params.columns]
        return frame[getattr(part.isna(), params.how)(axis=1)]

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        return f"{output} = {inputs[0]}[{_any_missing(params, inputs[0])}]"

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
        mask = ast.unparse(value.slice)
        for how in ("any", "all"):
            if mask == f"{frame}.isna().{how}(axis=1)":
                return base.Match(cls.Params(how=how), (frame,), output)
            prefix, suffix = f"{frame}[", f"].isna().{how}(axis=1)"
            if mask.startswith(prefix) and mask.endswith(suffix):
                try:
                    columns = ast.literal_eval(mask[len(prefix) : -len(suffix)])
                except ValueError, SyntaxError:
                    return None
                if not isinstance(columns, list):
                    return None
                return base.Match(cls.Params(how=how, columns=columns), (frame,), output)
        return None


def _is_nan(frame: Frame) -> Frame:
    return frame != frame  # noqa: PLR0124


class NanToMissing(base.Op):
    """`df.mask(lambda d: d != d)`: NaN is the only value not equal to itself.

    Nulls compare as null (not True), so they stay; non-float columns are unchanged.
    """

    id = "nan_to_missing"
    title = _("NaN to missing")
    description = _(
        "Turn NaN ('not a number') values of float columns into missing values, so missing"
        " value ops see them."
    )
    category = categories.NAN
    icon = "mdi.help-circle-outline"

    class Params(base.Params):
        columns: list[str] | None = _subset()

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        frame = inputs[0]
        if params.columns is None:
            return frame.mask(_is_nan)
        return frame.assign(**frame[params.columns].mask(_is_nan))

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        frame = inputs[0]
        if params.columns is None:
            return f"{output} = {frame}.mask(lambda d: d != d)"
        part = f"{frame}[{base.literal(params.columns)}]"
        return f"{output} = {frame}.assign(**{part}.mask(lambda d: d != d))"

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        text = ast.unparse(value)
        for frame in bound:
            if text == f"{frame}.mask(lambda d: d != d)":
                return base.Match(cls.Params(), (frame,), output)
            prefix, suffix = f"{frame}.assign(**{frame}[", "].mask(lambda d: d != d))"
            if text.startswith(prefix) and text.endswith(suffix):
                try:
                    columns = ast.literal_eval(text[len(prefix) : -len(suffix)])
                except ValueError, SyntaxError:
                    return None
                if not isinstance(columns, list):
                    return None
                return base.Match(cls.Params(columns=columns), (frame,), output)
        return None
