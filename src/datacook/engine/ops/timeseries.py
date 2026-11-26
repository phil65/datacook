"""Time series ops, index-free: the time is a column named in the params.

Set time column, resample (aggregate per interval, optionally per group), upsample, seconds
since start, gaps, rolling / expanding windows, tolerance bands, shift / diff / pct change.
The old pandastools accessor ops (`index_to_secs`, `detect_gaps`, `tolerance_bands`) are
plain pandas expressions here. See `datacook.engine.timecol` for the time column.
"""

import ast
import keyword
from typing import TYPE_CHECKING, Any, Literal, Self

from pydantic import Field, model_validator

from datacook.engine import categories
from datacook.engine.ops import base, series
from datacook.engine.ops.combine import Aggregation
from datacook.engine.timecol import TIME_COLUMN, is_datetime
from datacook.i18n import N_, _


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import pandas as pd

    from datacook.engine.frames import Frame


def _time_field(default: Any = ..., title: str = N_("Time column")) -> Any:
    return Field(default, title=title, json_schema_extra=TIME_COLUMN)


def _check_column(frame: Frame, column: str) -> None:
    if column not in frame.columns:
        raise base.OpError(f"unknown column: {column!r}")


class SetTimeColumn(base.Op):
    id = "set_time_column"
    title = _("Use as time column")
    description = _(
        "Make a date / time (or numeric) column the time of the table: rows are sorted by "
        "it and time series steps use it by default."
    )
    category = categories.TIMESERIES
    icon = "mdi.clock-outline"

    class Params(base.Params):
        time_column: str = _time_field()

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        frame = inputs[0]
        _check_column(frame, params.time_column)
        import pandas as pd

        dtype = frame[params.time_column].dtype
        if not (is_datetime(str(dtype)) or pd.api.types.is_numeric_dtype(dtype)):
            msg = f"{params.time_column!r} is {dtype}: convert it to date / time first"
            raise base.OpError(msg)
        return frame.sort_values(params.time_column, kind="stable", ignore_index=True)

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        column = base.literal(params.time_column)
        return f'{output} = {inputs[0]}.sort_values({column}, kind="stable", ignore_index=True)'

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:  # noqa: PLR0911
        assign = base.assignment(stmt)
        if assign is None:
            return None
        chain = series.unchain(assign[1])
        if chain is None:
            return None
        root, links = chain
        if not (isinstance(root, ast.Name) and root.id in bound and len(links) == 1):
            return None
        call = links[0]
        if call.kind != "call" or call.name != "sort_values" or len(call.args) != 1:
            return None
        try:
            args, _kwargs = call.literal_args()
        except ValueError:
            return None
        if not isinstance(args[0], str):
            return None
        params = cls.Params(time_column=args[0])
        return series.confirm(cls, params, [root.id], assign[0], stmt)


# --- resample ----------------------------------------------------------------------------

FREQ_DESCRIPTION = N_("e.g. 10s, 1min, 1h, 1D, 1W, 1MS (month start)")


class Resample(base.Op):
    id = "resample"
    title = _("Resample")
    description = _(
        "Aggregate the rows per time interval (e.g. mean per minute), optionally per group."
    )
    category = categories.TIMESERIES
    icon = "mdi.chart-timeline"

    class Params(base.Params):
        time_column: str = _time_field()
        rule: str = Field("1min", title=N_("Interval"), min_length=1, description=FREQ_DESCRIPTION)
        aggregations: list[Aggregation] = Field(title=N_("Aggregations"), min_length=1)
        by: list[str] | None = Field(
            None, title=N_("Per group of"), json_schema_extra={"widget": "columns"}
        )
        closed: Literal["left", "right"] | None = Field(None, title=N_("Closed side"))
        label: Literal["left", "right"] | None = Field(None, title=N_("Label side"))

    @classmethod
    def _options(cls, params: Params) -> dict[str, Any]:
        return {k: v for k in ("closed", "label") if (v := getattr(params, k)) is not None}

    @classmethod
    def _named(cls, params: Params) -> dict[str, tuple[str, str]]:
        return {a.output_name: (a.column, a.func) for a in params.aggregations}

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        import pandas as pd

        frame = inputs[0]
        _check_column(frame, params.time_column)
        if params.by:
            grouper = pd.Grouper(key=params.time_column, freq=params.rule, **cls._options(params))
            grouped: Any = frame.groupby([*params.by, grouper])
        else:
            grouped = frame.resample(params.rule, on=params.time_column, **cls._options(params))
        return grouped.agg(**cls._named(params)).reset_index()

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        var = inputs[0]
        if params.by:
            grouper = base.format_call(
                "pd.Grouper",
                [],
                {"key": params.time_column, "freq": params.rule, **cls._options(params)},
            )
            keys = ", ".join([*map(base.literal, params.by), grouper])
            head = f"{var}.groupby([{keys}])"
        else:
            kwargs = {"on": params.time_column, **cls._options(params)}
            head = base.format_call(f"{var}.resample", [base.literal(params.rule)], kwargs)
        named = cls._named(params)
        identifiers = all(n.isidentifier() and not keyword.iskeyword(n) for n in named)
        agg = (
            base.format_call(".agg", [], named, 4)
            if identifiers
            else f".agg(**{base.literal(named)})"
        )
        line = f"{output} = {head}{agg}.reset_index()"
        if len(line) <= base.LINE_LENGTH and "\n" not in line:
            return line
        # one method per line, like ruff formats long chains
        head, agg = head.replace("\n", "\n    "), agg.replace("\n", "\n    ")
        return f"{output} = (\n    {head}\n    {agg}\n    .reset_index()\n)"

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:  # noqa: PLR0911
        assign = base.assignment(stmt)
        if assign is None:
            return None
        chain = series.unchain(assign[1])
        if chain is None:
            return None
        root, links = chain
        if not (
            isinstance(root, ast.Name)
            and root.id in bound
            and len(links) == 3  # noqa: PLR2004
            and [link.name for link in links[1:]] == ["agg", "reset_index"]
            and all(link.kind == "call" for link in links)
        ):
            return None
        head, agg = links[0], links[1]
        try:
            named: dict[str, Any] = {}
            for kw in agg.kwargs.items():
                named[kw[0]] = base.literal_value(kw[1])
            if agg.args:
                return None
            fields: dict[str, Any] = {}
            if head.name == "resample" and len(head.args) == 1:
                [rule], kwargs = head.literal_args()
                fields = {"rule": rule, "time_column": kwargs.pop("on", None), **kwargs}
            elif (
                head.name == "groupby"
                and len(head.args) == 1
                and isinstance(head.args[0], ast.List)
            ):
                *keys, grouper = head.args[0].elts
                if not (
                    isinstance(grouper, ast.Call) and base.dotted_name(grouper.func) == "pd.Grouper"
                ):
                    return None
                options = {
                    kw.arg: base.literal_value(kw.value) for kw in grouper.keywords if kw.arg
                }
                fields = {
                    "by": [base.literal_value(k) for k in keys],
                    "time_column": options.pop("key", None),
                    "rule": options.pop("freq", None),
                    **options,
                }
            else:
                return None
        except ValueError:
            return None
        aggregations = []
        for name, spec in named.items():
            if not (isinstance(spec, tuple) and len(spec) == 2):  # noqa: PLR2004
                return None
            column, func = spec
            default = f"{column}_{func}"
            aggregations.append(
                Aggregation(column=column, func=func, name=None if name == default else name)
            )
        params = cls.Params(aggregations=aggregations, **fields)
        return series.confirm(cls, params, [root.id], assign[0], stmt)


class Upsample(base.Op):
    id = "upsample"
    title = _("Upsample")
    description = _(
        "One row per time interval (finer than the data): new rows are filled forward, "
        "backward, from the nearest row, interpolated or left missing."
    )
    category = categories.TIMESERIES
    icon = "mdi.chart-timeline-variant-shimmer"

    class Params(base.Params):
        time_column: str = _time_field()
        rule: str = Field("1s", title=N_("Interval"), min_length=1, description=FREQ_DESCRIPTION)
        method: Literal["asfreq", "ffill", "bfill", "nearest", "interpolate"] = Field(
            "ffill", title=N_("Fill new rows")
        )

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        frame = inputs[0]
        _check_column(frame, params.time_column)
        resampler = frame.set_index(params.time_column).resample(params.rule)
        return getattr(resampler, params.method)().reset_index()

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        var = inputs[0]
        column, rule = base.literal(params.time_column), base.literal(params.rule)
        return (
            f"{output} = {var}.set_index({column}).resample({rule}).{params.method}().reset_index()"
        )

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        assign = base.assignment(stmt)
        if assign is None:
            return None
        chain = series.unchain(assign[1])
        if chain is None:
            return None
        root, links = chain
        if not (
            isinstance(root, ast.Name)
            and root.id in bound
            and len(links) == 4  # noqa: PLR2004
            and [link.name for link in (links[0], links[1], links[3])]
            == ["set_index", "resample", "reset_index"]
            and all(link.kind == "call" and len(link.args) <= 1 for link in links)
            and links[0].args
            and links[1].args
        ):
            return None
        try:
            column = base.literal_value(links[0].args[0])
            rule = base.literal_value(links[1].args[0])
            params = cls.Params(time_column=column, rule=rule, method=links[2].name)  # ty: ignore[invalid-argument-type]
        except ValueError:
            return None
        return series.confirm(cls, params, [root.id], assign[0], stmt)


# --- derived columns ---------------------------------------------------------------------


def _single_assign(
    stmt: ast.stmt, bound: Mapping[str, Any]
) -> tuple[str, str, str, ast.expr] | None:
    """`(output, input, name, expr)` of `out = var.assign(name=expr)`."""
    found = series.assigned(stmt, bound)
    if found is None or len(found[2]) != 1:
        return None
    output, var, [(name, node)] = found
    return output, var, name, node


def _first_column(node: ast.expr, var: str) -> str | None:
    for sub in ast.walk(node):
        if (column := series.column_of(sub, var)) is not None:
            return column
    return None


class SecondsSinceStart(base.Op):
    """Old pandastools `index_to_secs`, as a column."""

    id = "seconds_since_start"
    title = _("Seconds since start")
    description = _("New column: seconds since the earliest time (e.g. for x axes of plots).")
    category = categories.TIMESERIES
    icon = "mdi.timer-outline"

    class Params(base.Params):
        time_column: str = _time_field()
        name: str = Field("secs", title=N_("New column"), min_length=1)

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        frame = inputs[0]
        _check_column(frame, params.time_column)
        time = frame[params.time_column]
        return frame.assign(**{params.name: (time - time.min()).dt.total_seconds()})

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        var = inputs[0]
        time = series.column_code(var, params.time_column)
        return series.assign_code(
            var, output, {params.name: f"({time} - {time}.min()).dt.total_seconds()"}
        )

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        found = _single_assign(stmt, bound)
        if found is None:
            return None
        output, var, name, node = found
        column = _first_column(node, var)
        if column is None:
            return None
        params = cls.Params(time_column=column, name=name)
        return series.confirm(cls, params, [var], output, stmt)


class DetectGaps(base.Op):
    """Old pandastools `detect_gaps` / time gaps, on a column."""

    id = "detect_gaps"
    title = _("Number segments between gaps")
    description = _(
        "New column numbering the segments of the data (1, 2, ...): a new segment starts "
        "where the time (or a numeric column) jumps by more than the maximum gap."
    )
    category = categories.TIMESERIES
    icon = "mdi.arrow-split-vertical"

    class Params(base.Params):
        time_column: str = _time_field(title=N_("Column"))
        max_gap: str | float = Field(
            "1s",
            title=N_("Maximum gap"),
            description=N_("A duration (e.g. 1s, 5min) for date / time, a number otherwise."),
        )
        name: str = Field("segment", title=N_("New column"), min_length=1)

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        import pandas as pd

        frame = inputs[0]
        _check_column(frame, params.time_column)
        gap = pd.Timedelta(params.max_gap) if isinstance(params.max_gap, str) else params.max_gap
        jumps = frame[params.time_column].diff().gt(gap).fillna(False).astype("int64")
        return frame.assign(**{params.name: jumps.cumsum() + 1})

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        var = inputs[0]
        gap = (
            f"pd.Timedelta({base.literal(params.max_gap)})"
            if isinstance(params.max_gap, str)
            else base.literal(params.max_gap)
        )
        time = series.column_code(var, params.time_column)
        expr = f'{time}.diff().gt({gap}).fillna(False).astype("int64").cumsum() + 1'
        return series.assign_code(var, output, {params.name: expr})

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        found = _single_assign(stmt, bound)
        if found is None:
            return None
        output, var, name, node = found
        column = _first_column(node, var)
        gt = next(
            (
                sub
                for sub in ast.walk(node)
                if isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "gt"
                and len(sub.args) == 1
            ),
            None,
        )
        if column is None or gt is None:
            return None
        arg = gt.args[0]
        try:
            if isinstance(arg, ast.Call) and base.dotted_name(arg.func) == "pd.Timedelta":
                max_gap = base.literal_value(arg.args[0])
            else:
                max_gap = base.literal_value(arg)
        except ValueError, IndexError:
            return None
        params = cls.Params(time_column=column, max_gap=max_gap, name=name)
        return series.confirm(cls, params, [var], output, stmt)


# --- windows -----------------------------------------------------------------------------

type WindowFunc = Literal["mean", "sum", "min", "max", "median", "std", "var", "count"]


class _WindowParams(series.ColumnParams):
    window: int | str = Field(
        5,
        title=N_("Window"),
        description=N_("Number of rows, or a duration like 10s / 5min (needs a time column)."),
    )
    func: WindowFunc = Field("mean", title=N_("Function"))
    min_periods: int | None = Field(
        None,
        title=N_("Minimum values"),
        ge=0,
        description=N_("Fewer values give a missing result."),
    )
    center: bool = Field(False, title=N_("Centered window"))
    time_column: str | None = _time_field(None)

    @model_validator(mode="after")
    def _duration_needs_time(self) -> Self:
        if isinstance(self.window, str) and self.time_column is None:
            raise ValueError("a duration window needs a time column")
        return self


class Rolling(series.ColumnOp):
    id = "rolling"
    title = _("Rolling window")
    description = _(
        "Moving mean, sum, minimum, ... over a window of rows or of a duration (smoothing)."
    )
    category = categories.TIMESERIES
    icon = "mdi.chart-bell-curve-cumulative"

    class Params(_WindowParams):
        pass

    @classmethod
    def _kwargs(cls, params: Params) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if params.time_column is not None:
            kwargs["on"] = params.time_column
        if params.min_periods is not None:
            kwargs["min_periods"] = params.min_periods
        if params.center:
            kwargs["center"] = True
        return kwargs

    @classmethod
    def series(cls, params: Params, frame: Frame, column: str) -> pd.Series:
        kwargs = cls._kwargs(params)
        if params.time_column is not None:
            window = frame.rolling(params.window, **kwargs)[column]
        else:
            window = frame[column].rolling(params.window, **kwargs)
        return getattr(window, params.func)()

    @classmethod
    def expr(cls, params: Params, var: str, column: str) -> str:
        kwargs = cls._kwargs(params)
        args = [base.literal(params.window)]
        if params.time_column is not None:
            window = base.format_call(f"{var}.rolling", args, kwargs) + f"[{base.literal(column)}]"
        else:
            window = base.format_call(f"{series.column_code(var, column)}.rolling", args, kwargs)
        return f"{window}.{params.func}()"

    @classmethod
    def match_expr(cls, node: ast.expr, var: str) -> tuple[str, dict[str, Any]] | None:
        chain = series.unchain(node)
        if chain is None:
            return None
        root, links = chain
        if not (isinstance(root, ast.Name) and root.id == var and len(links) == 3):  # noqa: PLR2004
            return None
        if links[0].kind == "item":
            column, rolling = series.item_key(links[0]), links[1]
        else:
            rolling, column = links[0], series.item_key(links[1])
        func = links[2]
        if rolling.name != "rolling" or func.kind != "call" or func.args or func.kwargs:
            return None
        args, kwargs = rolling.literal_args()
        if len(args) != 1 or not isinstance(column, str):
            return None
        options = {"window": args[0], "func": func.name, **kwargs}
        if "on" in options:
            options["time_column"] = options.pop("on")
        return column, options


class Expanding(series.ColumnOp):
    id = "expanding"
    title = _("Cumulative (expanding window)")
    description = _("Mean, sum, minimum, ... of all values from the first row up to each row.")
    category = categories.TIMESERIES
    icon = "mdi.chart-line-stacked"

    class Params(series.ColumnParams):
        func: WindowFunc = Field("sum", title=N_("Function"))
        min_periods: int = Field(1, title=N_("Minimum values"), ge=0)

    @classmethod
    def _kwargs(cls, params: Params) -> dict[str, Any]:
        return {} if params.min_periods == 1 else {"min_periods": params.min_periods}

    @classmethod
    def series(cls, params: Params, frame: Frame, column: str) -> pd.Series:
        return getattr(frame[column].expanding(**cls._kwargs(params)), params.func)()

    @classmethod
    def expr(cls, params: Params, var: str, column: str) -> str:
        window = base.format_call(
            f"{series.column_code(var, column)}.expanding", [], cls._kwargs(params)
        )
        return f"{window}.{params.func}()"

    @classmethod
    def match_expr(cls, node: ast.expr, var: str) -> tuple[str, dict[str, Any]] | None:
        chain = series.unchain(node)
        if chain is None:
            return None
        column = series.chain_column(*chain, var)
        links = chain[1]
        if column is None or len(links) != 3 or links[1].name != "expanding":  # noqa: PLR2004
            return None
        func = links[2]
        if func.kind != "call" or func.args or func.kwargs or links[1].args:
            return None
        _args, kwargs = links[1].literal_args()
        return column, {"func": func.name, **kwargs}


class Shift(series.SeriesOp):
    id = "shift"
    title = _("Shift values")
    description = _("Move values down (positive periods) or up (negative) by rows.")
    category = categories.TIMESERIES
    icon = "mdi.arrow-expand-down"
    method = "shift"

    class Params(series.ColumnParams):
        periods: int = Field(1, title=N_("Rows"))
        fill_value: float | None = Field(None, title=N_("Value for new cells"))


class Diff(series.SeriesOp):
    id = "diff"
    title = _("Difference")
    description = _("Difference to the value n rows before.")
    category = categories.TIMESERIES
    icon = "mdi.delta"
    method = "diff"

    class Params(series.ColumnParams):
        periods: int = Field(1, title=N_("Rows"))


class PctChange(series.SeriesOp):
    id = "pct_change"
    title = _("Relative change")
    description = _("Relative change to the value n rows before (0.1 = +10 %).")
    category = categories.TIMESERIES
    icon = "mdi.percent-outline"
    method = "pct_change"

    class Params(series.ColumnParams):
        periods: int = Field(1, title=N_("Rows"))


class ToleranceBands(base.Op):
    """Old pandastools `tolerance_bands`: lower = min(rolling min, x * (1 - pct)), upper alike."""

    id = "tolerance_bands"
    title = _("Tolerance bands")
    description = _(
        "New columns <column>_lower / _upper: the centered rolling minimum / maximum, at "
        "least the given fraction below / above each value."
    )
    category = categories.TIMESERIES
    icon = "mdi.chart-bell-curve"

    class Params(base.Params):
        columns: list[str] = Field(
            title=N_("Columns"), min_length=1, json_schema_extra={"widget": "columns"}
        )
        window: int | str = Field(
            5,
            title=N_("Window"),
            description=N_("Number of rows, or a duration like 10s / 5min (needs a time column)."),
        )
        pct: float = Field(0.1, title=N_("Minimum distance (fraction)"), ge=0, le=1)
        time_column: str | None = _time_field(None)

        @model_validator(mode="after")
        def _duration_needs_time(self) -> Self:
            if isinstance(self.window, str) and self.time_column is None:
                raise ValueError("a duration window needs a time column")
            return self

    @classmethod
    def _kwargs(cls, params: Params) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"center": True, "min_periods": 1}
        if params.time_column is not None:
            kwargs["on"] = params.time_column
        return kwargs

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        frame = inputs[0]
        values: dict[str, pd.Series] = {}
        for column in params.columns:
            _check_column(frame, column)
            if params.time_column is not None:
                window = frame.rolling(params.window, **cls._kwargs(params))[column]
            else:
                window = frame[column].rolling(params.window, **cls._kwargs(params))
            values[f"{column}_lower"] = window.min().clip(upper=frame[column] * (1 - params.pct))
            values[f"{column}_upper"] = window.max().clip(lower=frame[column] * (1 + params.pct))
        return frame.assign(**values)

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        var = inputs[0]
        args = [base.literal(params.window)]
        values = {}
        pct = base.literal(params.pct)
        for column in params.columns:
            source = series.column_code(var, column)
            if params.time_column is not None:
                window = base.format_call(f"{var}.rolling", args, cls._kwargs(params))
                window += f"[{base.literal(column)}]"
            else:
                window = base.format_call(f"{source}.rolling", args, cls._kwargs(params))
            values[f"{column}_lower"] = f"{window}.min().clip(upper={source} * (1 - {pct}))"
            values[f"{column}_upper"] = f"{window}.max().clip(lower={source} * (1 + {pct}))"
        return series.assign_code(var, output, values)

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:
        found = series.assigned(stmt, bound)
        if found is None:
            return None
        output, var, pairs = found
        if len(pairs) % 2 or not pairs:
            return None
        columns = [name.removesuffix("_lower") for name, _node in pairs[::2]]
        node = pairs[0][1]
        rolling = next(
            (
                sub
                for sub in ast.walk(node)
                if isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "rolling"
            ),
            None,
        )
        clip = node if isinstance(node, ast.Call) else None
        try:
            if rolling is None or clip is None or len(rolling.args) != 1:
                return None
            window = base.literal_value(rolling.args[0])
            on = next(
                (base.literal_value(k.value) for k in rolling.keywords if k.arg == "on"), None
            )
            factor = clip.keywords[0].value if clip.keywords else None
            if not (isinstance(factor, ast.BinOp) and isinstance(factor.right, ast.BinOp)):
                return None
            pct = base.literal_value(factor.right.right)
        except ValueError:
            return None
        params = cls.Params(columns=columns, window=window, pct=pct, time_column=on)
        return series.confirm(cls, params, [var], output, stmt)
