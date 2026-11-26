"""Statistics ops: describe, variances, correlations, modes, value counts, ranks, bins.

Correlations also with another table; bins via `pd.cut`.

Summary results are new tables like every other step: row labels become a column
(`statistic` / `column`), e.g. `df.corr().reset_index(names="column")`. Rank and binning
are column ops (`ops/series.py`): results go to `<column>_rank` / `<column>_bin` by default.
"""

import ast
from typing import TYPE_CHECKING, Any, Literal, Self

from pydantic import Field, model_validator

from datacook.engine import categories, frames
from datacook.engine.ops import base, series
from datacook.i18n import N_, _


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from datacook.engine.frames import Frame


type CorrelationMethod = Literal["pearson", "spearman", "kendall"]


def _subset() -> Any:
    return Field(None, title=N_("Columns (empty: all)"), json_schema_extra={"widget": "columns"})


def _method() -> Any:
    return Field(
        "pearson",
        title=N_("Method"),
        description=N_("pearson: linear; spearman / kendall: rank correlation."),
    )


def _numeric_only() -> Any:
    return Field(True, title=N_("Numeric columns only"))


class SubsetCallOp(base.CallOp):
    """A frame method on all columns or on the `columns` subset, with a new table as result.

    `out = df[["x", "y"]].corr(method="spearman").reset_index(names="column")` (`then` is
    the tail, `finish()` its execution). `columns` is never passed to the method.
    """

    category = categories.STATS
    icon = "mdi.chart-box-outline"

    @classmethod
    def call_args(cls, params: base.Params) -> tuple[list[Any], dict[str, Any]]:
        args, kwargs = base.call_arguments(params, cls.positional, cls.always, ("columns",))
        return args, {**cls.fixed, **kwargs}

    @classmethod
    def apply(cls, params: Any, *inputs: Frame) -> Frame:
        frame = inputs[0]
        if params.columns is not None:
            missing = [c for c in params.columns if c not in frame.columns]
            if missing:
                raise base.OpError(f"unknown columns: {missing}")
            frame = frame[params.columns]
        args, kwargs = cls.call_args(params)
        assert cls.method is not None
        result = cls.finish(params, getattr(frame, cls.method)(*args, **kwargs))
        if not frames.is_frame(result):
            msg = f"{cls.id} returned {type(result).__name__}, not a frame"
            raise base.OpError(msg)
        return result

    @classmethod
    def to_code(cls, params: Any, inputs: Sequence[str], output: str) -> str:
        source = inputs[0]
        if params.columns is not None:
            source = f"{source}[{base.literal(params.columns)}]"
        args, kwargs = cls.call_args(params)
        func = f"{source}.{cls.method}"
        width = len(output) + 3 + len(cls.then)  # the tail goes on the last line
        call = base.format_call(func, list(map(base.literal, args)), kwargs, width)
        return f"{output} = {call}{cls.then}"

    @classmethod
    def from_code(cls, stmt: ast.stmt, bound: Mapping[str, Any]) -> base.Match | None:  # noqa: PLR0911
        assign = base.assignment(stmt)
        if assign is None:
            return None
        output, value = assign
        if cls.then:
            value = base.strip_tail(value, cls.then)
        chain = series.unchain(value) if value is not None else None
        if chain is None:
            return None
        root, links = chain
        if not (isinstance(root, ast.Name) and root.id in bound and 1 <= len(links) <= 2):  # noqa: PLR2004
            return None
        call = links[-1]
        if call.kind != "call" or call.name != cls.method or "columns" in call.kwargs:
            return None
        try:
            columns = series.item_key(links[0]) if len(links) == 2 else None  # noqa: PLR2004
            args, kwargs = call.literal_args()
        except ValueError:  # not literal: user code
            return None
        if columns is not None and not isinstance(columns, list):
            return None
        params = cls.params_from_call(args, {**kwargs, "columns": columns})
        return None if params is None else base.Match(params, (root.id,), output)


class Describe(SubsetCallOp):
    id = "describe"
    title = _("Descriptive statistics")
    description = _(
        "Count, mean, standard deviation, minimum, quartiles and maximum of each column"
        " (text columns: count, unique values, most frequent value)."
    )
    method = "describe"
    then = '.reset_index(names="statistic")'

    class Params(base.Params):
        columns: list[str] | None = _subset()
        include: Literal["all"] | None = Field(
            None,
            title=N_("Include"),
            description=N_("Empty: numeric columns only (if any); all: every column."),
        )
        percentiles: list[float] | None = Field(
            None, title=N_("Percentiles"), description=N_("Between 0 and 1; empty: quartiles.")
        )

    @classmethod
    def finish(cls, params: Any, result: Any) -> Any:
        return result.reset_index(names="statistic")


class Variance(SubsetCallOp):
    id = "var"
    title = _("Variances")
    description = _("The variance of each numeric column.")
    method = "var"
    always = ("numeric_only",)
    then = '.rename_axis("column").reset_index(name="variance")'

    class Params(base.Params):
        columns: list[str] | None = _subset()
        ddof: int = Field(
            1, title=N_("Delta degrees of freedom"), ge=0, description=N_("1: sample variance.")
        )
        skipna: bool = Field(True, title=N_("Skip missing values"))
        numeric_only: bool = _numeric_only()

    @classmethod
    def finish(cls, params: Any, result: Any) -> Any:
        return result.rename_axis("column").reset_index(name="variance")


class Covariance(SubsetCallOp):
    id = "cov"
    title = _("Covariances")
    description = _("Covariance matrix of the numeric columns (pairwise, missing values skipped).")
    method = "cov"
    always = ("numeric_only",)
    then = '.reset_index(names="column")'

    class Params(base.Params):
        columns: list[str] | None = _subset()
        min_periods: int | None = Field(None, title=N_("Minimum values"), ge=1)
        ddof: int = Field(1, title=N_("Delta degrees of freedom"), ge=0)
        numeric_only: bool = _numeric_only()

    @classmethod
    def finish(cls, params: Any, result: Any) -> Any:
        return result.reset_index(names="column")


class Correlation(SubsetCallOp):
    id = "corr"
    title = _("Correlations")
    description = _("Correlation matrix of the numeric columns (Pearson, Spearman or Kendall).")
    icon = "mdi.chart-scatter-plot"
    method = "corr"
    always = ("numeric_only",)
    then = '.reset_index(names="column")'

    class Params(base.Params):
        columns: list[str] | None = _subset()
        method: CorrelationMethod = _method()
        min_periods: int = Field(1, title=N_("Minimum values"), ge=1)
        numeric_only: bool = _numeric_only()

    @classmethod
    def finish(cls, params: Any, result: Any) -> Any:
        return result.reset_index(names="column")


class Mode(SubsetCallOp):
    id = "mode"
    title = _("Most frequent values")
    description = _(
        "The most frequent value(s) of each column (mode): one row per mode, missing values"
        " where a column has fewer modes."
    )
    method = "mode"

    class Params(base.Params):
        columns: list[str] | None = _subset()
        numeric_only: bool = Field(False, title=N_("Numeric columns only"))
        dropna: bool = Field(True, title=N_("Ignore missing values"))


class ValueCounts(base.CallOp):
    id = "value_counts"
    title = _("Value counts")
    description = _(
        "Count the rows per value (or per combination of values) of columns: a new table"
        " with the values and a count (or share) column."
    )
    category = categories.STATS
    icon = "mdi.counter"
    method = "value_counts"
    then = ".reset_index()"

    class Params(base.Params):
        subset: list[str] | None = _subset()
        normalize: bool = Field(False, title=N_("Shares instead of counts"))
        sort: bool = Field(True, title=N_("Sort by count"))
        ascending: bool = Field(False, title=N_("Ascending"))
        dropna: bool = Field(True, title=N_("Ignore missing values"))

    @classmethod
    def finish(cls, params: Any, result: Any) -> Any:
        return result.reset_index()


class CorrelationWith(base.CallOp):
    """`df.corrwith(other)`: columns matched by name, rows by position (no index).

    Pearson only: pandas computes Spearman / Kendall here with scipy (no dependency).
    """

    id = "corrwith"
    title = _("Correlation with another table")
    description = _(
        "Pearson correlation of each column with the column of the same name in a second"
        " table (rows matched by position)."
    )
    category = categories.STATS
    icon = "mdi.chart-scatter-plot"
    n_inputs = 2
    method = "corrwith"
    always = ("numeric_only",)
    then = '.rename_axis("column").reset_index(name="correlation")'

    class Params(base.Params):
        drop: bool = Field(False, title=N_("Drop columns missing in one table"))
        numeric_only: bool = _numeric_only()

    @classmethod
    def finish(cls, params: Any, result: Any) -> Any:
        return result.rename_axis("column").reset_index(name="correlation")


class Rank(series.SeriesOp):
    id = "rank"
    title = _("Rank values")
    description = _("The rank of each value within its column (1 = smallest).")
    category = categories.STATS
    icon = "mdi.podium"
    method = "rank"

    class Params(series.ColumnParams):
        suffix: str = Field(
            "_rank",
            title=N_("Suffix for new columns"),
            description=N_("Empty: replace the columns. Otherwise the results are new columns."),
        )
        method: Literal["average", "min", "max", "first", "dense"] = Field(
            "average", title=N_("Ties"), description=N_("Rank of equal values.")
        )
        na_option: Literal["keep", "top", "bottom"] = Field("keep", title=N_("Missing values"))
        ascending: bool = Field(True, title=N_("Ascending"))
        pct: bool = Field(False, title=N_("As share (0 to 1)"))


class Bin(series.SeriesOp):
    """`pd.cut`: equal-width bins (a number) or bins between edges (a list)."""

    id = "cut"
    title = _("Bin values")
    description = _(
        "Put numbers into intervals: a number of equal-width bins, or bins between given"
        " edges (histogram classes)."
    )
    category = categories.STATS
    icon = "mdi.chart-histogram"
    function = "pd.cut"
    positional = ("bins",)

    class Params(series.ColumnParams):
        suffix: str = Field(
            "_bin",
            title=N_("Suffix for new columns"),
            description=N_("Empty: replace the columns. Otherwise the results are new columns."),
        )
        bins: int | list[float] = Field(
            title=N_("Bins"),
            description=N_("A number of equal-width bins, or the bin edges (ascending)."),
        )
        right: bool = Field(True, title=N_("Bins include their right edge"))
        include_lowest: bool = Field(False, title=N_("First bin includes its left edge"))
        labels: list[str] | None = Field(
            None, title=N_("Labels"), description=N_("One per bin; empty: the intervals.")
        )
        precision: int = Field(3, title=N_("Precision of the interval labels"), ge=0)

        @model_validator(mode="after")
        def _check_bins(self) -> Self:
            if isinstance(self.bins, int):
                if self.bins < 1:
                    raise ValueError("at least one bin")
                n = self.bins
            else:
                if (
                    len(self.bins) < 2  # noqa: PLR2004
                    or any(a >= b for a, b in zip(self.bins, self.bins[1:]))
                ):
                    raise ValueError("bin edges: at least two, ascending")
                n = len(self.bins) - 1
            if self.labels is not None and len(self.labels) != n:
                raise ValueError(f"{n} labels needed")
            return self
