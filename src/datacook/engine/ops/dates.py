"""Date and time ops: convert to datetime, parts, format, time zones, rounding."""

import ast
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field

from datacook.engine import categories
from datacook.engine.ops import base, series
from datacook.i18n import N_, _


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import pandas as pd

    from datacook.engine.frames import Frame


class ToDatetime(series.SeriesOp):
    id = "to_datetime"
    title = _("Convert to date / time")
    description = _("Parse text or numbers (epoch values) into date / time values.")
    category = categories.DATETIME
    icon = "mdi.calendar-arrow-right"
    function = "pd.to_datetime"

    class Params(series.ColumnParams):
        format: str | None = Field(
            None,
            title=N_("Format"),
            description=N_("strftime format like %d.%m.%Y %H:%M. Empty: detect."),
            examples=["%Y-%m-%d %H:%M:%S", "ISO8601", "mixed"],
        )
        dayfirst: bool = Field(False, title=N_("Day first (01.02. = 1 February)"))
        unit: Literal["D", "s", "ms", "us", "ns"] | None = Field(
            None, title=N_("Unit of numbers"), description=N_("For numbers since 1970-01-01.")
        )
        utc: bool = Field(False, title=N_("Convert to UTC"))
        errors: Literal["raise", "coerce"] = Field(
            "raise",
            title=N_("Invalid values"),
            description=N_("raise: fail; coerce: make them missing."),
        )


class FloatYearToDatetime(series.ColumnOp):
    """Old pandastools `float_year_to_datetime`: 2020.5 -> 2020-07-02 (365.25 days a year)."""

    id = "float_year_to_datetime"
    title = _("Decimal year to date / time")
    description = _("Convert decimal years (2020.5) into date / time values.")
    category = categories.DATETIME
    icon = "mdi.calendar-arrow-right"

    @classmethod
    def series(cls, params: Any, frame: Frame, column: str) -> pd.Series:
        import pandas as pd

        years = frame[column].astype("float64")
        start = pd.to_datetime((years // 1).astype("Int64").astype("string"), format="%Y")
        return start + pd.to_timedelta(years % 1 * 365.25, unit="D")

    @classmethod
    def expr(cls, params: Any, var: str, column: str) -> str:
        years = f'{series.column_code(var, column)}.astype("float64")'
        return (
            f'pd.to_datetime(({years} // 1).astype("Int64").astype("string"), format="%Y")'
            f' + pd.to_timedelta({years} % 1 * 365.25, unit="D")'
        )

    @classmethod
    def match_expr(cls, node: ast.expr, var: str) -> tuple[str, dict[str, Any]] | None:
        for sub in ast.walk(node):
            if (column := series.column_of(sub, var)) is not None:
                return column, {}  # the rest is checked by regenerating the code
        return None


type Part = Literal[
    "date",
    "time",
    "year",
    "quarter",
    "month",
    "day",
    "hour",
    "minute",
    "second",
    "day_of_week",
    "day_of_year",
    "month_name",
    "day_name",
]
NAMED_PARTS = ("month_name", "day_name")
"""Parts that are methods (localised names); the others are attributes."""


class DatetimeParts(base.Op):
    id = "dt_parts"
    title = _("Extract date / time parts")
    description = _(
        "New columns with the year, month, weekday, hour, ... of a date / time column "
        "(weekday: Monday = 0)."
    )
    category = categories.DATETIME
    icon = "mdi.calendar-search"

    class Params(base.Params):
        column: str = Field(title=N_("Column"), json_schema_extra={"widget": "column"})
        parts: list[Part] = Field(title=N_("Parts"), min_length=1)
        locale: str | None = Field(
            None,
            title=N_("Language of names"),
            description=N_("Locale for month / day names, e.g. de_DE.UTF-8. Empty: English."),
        )

    @classmethod
    def _kwargs(cls, params: Params) -> dict[str, Any]:
        return {} if params.locale is None else {"locale": params.locale}

    @classmethod
    def apply(cls, params: Params, *inputs: Frame) -> Frame:
        frame = inputs[0]
        dt = frame[params.column].dt
        values = {}
        for part in params.parts:
            value = getattr(dt, part)
            values[f"{params.column}_{part}"] = (
                value(**cls._kwargs(params)) if part in NAMED_PARTS else value
            )
        return frame.assign(**values)

    @classmethod
    def to_code(cls, params: Params, inputs: Sequence[str], output: str) -> str:
        var = inputs[0]
        dt = f"{series.column_code(var, params.column)}.dt"
        values = {
            f"{params.column}_{part}": (
                base.format_call(f"{dt}.{part}", [], cls._kwargs(params))
                if part in NAMED_PARTS
                else f"{dt}.{part}"
            )
            for part in params.parts
        }
        return series.assign_code(var, output, values)

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:  # noqa: PLR0911
        found = series.assigned(stmt, bound)
        if found is None:
            return None
        output, var, pairs = found
        columns: set[str] = set()
        parts: list[str] = []
        locale: Any = None
        for _name, node in pairs:
            chain = series.unchain(node)
            if chain is None:
                return None
            column = series.chain_column(*chain, var)
            links = chain[1]
            if column is None or len(links) != 3 or links[1] != series.Link("attr", "dt"):  # noqa: PLR2004
                return None
            columns.add(column)
            parts.append(links[2].name)
            if links[2].kind == "call":
                try:
                    _args, kwargs = links[2].literal_args()
                except ValueError:
                    return None
                locale = kwargs.get("locale")
        if len(columns) != 1:
            return None
        try:
            params = cls.Params(column=columns.pop(), parts=parts, locale=locale)  # ty: ignore[invalid-argument-type]
        except ValueError:
            return None  # e.g. another `.dt` attribute: user code
        return series.confirm(cls, params, [var], output, stmt)


class Strftime(series.SeriesOp):
    id = "dt_strftime"
    title = _("Date / time to text")
    description = _("Format date / time values as text (strftime format).")
    category = categories.DATETIME
    icon = "mdi.calendar-text"
    accessor = "dt"
    method = "strftime"
    positional = ("date_format",)

    class Params(series.ColumnParams):
        date_format: str = Field(
            "%Y-%m-%d", title=N_("Format"), min_length=1, examples=["%d.%m.%Y %H:%M"]
        )


class TzLocalize(series.SeriesOp):
    id = "tz_localize"
    title = _("Set time zone")
    description = _(
        "Declare the time zone of date / time values without one (or remove it: empty)."
    )
    category = categories.DATETIME
    icon = "mdi.map-clock"
    accessor = "dt"
    method = "tz_localize"
    positional = ("tz",)

    class Params(series.ColumnParams):
        tz: str | None = Field(title=N_("Time zone"), examples=["Europe/Berlin", "UTC"])
        ambiguous: Literal["raise", "NaT"] = Field(
            "raise",
            title=N_("Ambiguous times"),
            description=N_("Times that occur twice when daylight saving time ends."),
        )
        nonexistent: Literal["raise", "NaT", "shift_forward", "shift_backward"] = Field(
            "raise",
            title=N_("Nonexistent times"),
            description=N_("Times skipped when daylight saving time starts."),
        )


class TzConvert(series.SeriesOp):
    id = "tz_convert"
    title = _("Convert time zone")
    description = _("Convert date / time values with a time zone to another time zone.")
    category = categories.DATETIME
    icon = "mdi.earth"
    accessor = "dt"
    method = "tz_convert"
    positional = ("tz",)

    class Params(series.ColumnParams):
        tz: str | None = Field(
            title=N_("Time zone"),
            description=N_("Empty: UTC without a time zone."),
            examples=["Europe/Berlin", "UTC"],
        )


class RoundTime(series.SeriesOp):
    id = "dt_round"
    title = _("Round date / time")
    description = _("Round date / time values down, up or to the nearest multiple of a frequency.")
    category = categories.DATETIME
    icon = "mdi.clock-start"
    accessor = "dt"
    method_param = "how"
    positional = ("freq",)

    class Params(series.ColumnParams):
        how: Literal["floor", "round", "ceil"] = Field("floor", title=N_("Rounding"))
        freq: str = Field(
            "1min",
            title=N_("Frequency"),
            min_length=1,
            description=N_("e.g. 1s, 15min, 1h, 1D"),
        )
