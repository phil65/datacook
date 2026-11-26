from __future__ import annotations

from collections.abc import Callable, Hashable, Sequence
from typing import Any

import numpy as np
import pandas as pd
from pandastools import dtypes
from pydantic import Field

from datacook.constants import iconnames
from datacook.core import categories
from datacook.core.application import _
from datacook.methods import base, methods


WIN_TYPES = {
    None: _("Rectangle"),
    "boxcar": _("Boxcar"),
    "triang": _("Triangle"),
    "blackman": _("Blackman"),
    "hamming": _("Hamming"),
    "bartlett": _("Bartlett"),
    "parzen": _("Parzen"),
    "bohman": _("Bohman"),
    "blackmanharris": _("Blackman-Harris"),
    "nuttall": _("Nuttall"),
    "barthann": _("Bartlett-Hann"),
}

METHODS = {
    "sum": _("Sum"),
    "mean": _("Mean"),
    "min": _("Minimum"),
    "max": _("Maximum"),
    "corr": _("Correlation"),
    "cov": _("Covariance"),
    "var": _("Variance"),
    "std": _("Standard deviation"),
    "skew": _("Skew"),
    "kurt": _("Kurtosis"),
    "median": _("Median"),
}

ERRORS = {"raise": _("Raise"), "ignore": _("Ignore")}

REINDEX_METHODS = {
    None: _("Do not fill gaps"),
    "ffill": _("Forward fill"),
    "bfill": _("Backward fill"),
    "nearest": _("Nearest"),
}

ORDER_OPTS = {False: _("Descending"), True: _("Ascending")}

NA_POS = {"last": _("End"), "first": _("Beginning")}

NAN_CHOICES = {"all": _("All values are NA"), "any": _("Any value is NA")}

DROP_METHODS = {
    "first": _("Take first occurence"),
    "last": _("Take last occurence"),
    False: _("Drop all duplicates"),
}

RANDOM_STATE = {None: _("True"), 1: _("False")}

INTERPOLATE_METHODS = {"linear": _("Linear"), "time": _("Time"), "index": _("Index")}

RANK_METHODS = {
    "average": _("Average"),
    "min": _("Minimum"),
    "max": _("Maximum"),
    "first": _("First"),
    "dense": _("Dense"),
}

NA_OPTIONS = {"keep": _("Keep"), "top": _("Top"), "bottom": _("Bottom")}

CORRELATION_TYPES = {"pearson": "Pearson", "spearman": "Spearman", "kendall": "Kendall"}

KEEP_OPTS = {
    "first": _("Prioritize first occurrence"),
    "last": _("Prioritize last occurrence"),
}

FILL_OPTS = {None: _("Default (NaN)"), 0: "0"}

FILL_MODES = {"ffill": _("Forward-fill"), "bfill": _("Backward-fill")}

LIMIT_DIRECTIONS = {
    "forward": _("Forward"),
    "backward": _("Backward"),
    "both": _("Both"),
}

PIVOT_METHODS = dict(
    mean=_("Mean"),
    median=_("Median"),
    std=_("Standard deviation"),
    var=_("Variance"),
    sum=_("Sum"),
    prod=_("Product"),
    min=_("Minimum"),
    max=_("Maximum"),
    first=_("First"),
    last=_("Last"),
    count=_("Count"),
)

SIDE_OPTS = {None: _("Default"), "left": _("Left"), "right": _("Right")}

AXIS_ITEMS = {0: _("Index"), 1: _("Columns")}

PARSERS = dict(pandas="Pandas", python="Python")

SORT_ALGO = dict(quicksort="Quicksort", mergesort="Mergesort", heapsort="Heapsort")


class SelectDtypesMethod(methods.DatasetMethod):
    icon = iconnames.FILTER
    description = _("Select dtypes")
    short_desc = _("Select dtypes")
    obj = pd.DataFrame.select_dtypes
    category = categories.FilterCategory

    class Params(base.BaseModel):
        include: list[str] | None = Field(
            None,
            title=_("Dtypes to include"),
            mapping=dtypes.DType.get_dtypes(),
        )
        exclude: list[str] | None = Field(
            None,
            title=_("Dtypes to exclude"),
            mapping=dtypes.DType.get_dtypes(),
        )


class ConvertDtypesMethod(methods.DatasetMethod):
    icon = iconnames.DOWNCAST
    description = _("Detect and convert to the best possible data type for each feature.")
    short_desc = _("Convert Dtypes")
    obj = pd.DataFrame.convert_dtypes
    category = categories.ConversionCategory
    same_shape = True

    class Params(base.BaseModel):
        infer_objects: bool = Field(True, title=_("Infer objects"))
        convert_string: bool = Field(True, title=_("Convert strings"))
        convert_integer: bool = Field(True, title=_("Convert integers"))
        convert_boolean: bool = Field(True, title=_("Convert booleans"))


class IsNaMethod(methods.DatasetMethod):
    icon = iconnames.NAN
    description = _("Output a TRUE/FASE table indicating if the values are NA.")
    short_desc = _("Is NA")
    obj = pd.DataFrame.isna
    category = categories.NanCategory
    same_shape = True


class AbsMethod(methods.DatasetMethod):
    icon = iconnames.CALCULATIONS
    description = _("Returns dataframe with absolute numeric values.")
    short_desc = _("Absolute values")
    obj = pd.DataFrame.abs
    category = categories.GeneralCategory
    same_shape = True


class QueryMethod(methods.DatasetMethod):
    icon = iconnames.QUERY
    description = _("Query the columns of a DataFrame with a boolean expression.")
    short_desc = _("Query")
    obj = pd.DataFrame.query
    category = categories.GeneralCategory

    class Params(base.BaseModel):
        expr: str = Field(title=_("Expression"))
        parser: str = Field("pandas", title=_("Parser"), mapping=PARSERS)
        # target: Optional[object] = Field(None, title=_("target"))
        # inplace


class AddPrefixMethod(methods.DatasetMethod):
    icon = iconnames.SPLIT
    description = _("Add prefix to all features")
    short_desc = _("Add prefix")
    obj = pd.DataFrame.add_prefix
    category = categories.GeneralCategory
    same_shape = True

    class Params(base.BaseModel):
        prefix: str = Field(title=_("Prefix"), min_length=1)


class AddSuffixMethod(AddPrefixMethod):
    icon = iconnames.SPLIT
    description = _("Add suffix to all features")
    short_desc = _("Add suffix")
    obj = pd.DataFrame.add_suffix
    category = categories.GeneralCategory
    same_shape = True

    class Params(base.BaseModel):
        suffix: str = Field(title=_("Suffix"), min_length=1)


class ResetIndexMethod(methods.DatasetMethod):
    icon = iconnames.RESET_INDEX
    description = _("Reset indexes")
    short_desc = _("Reset index")
    obj = pd.DataFrame.reset_index
    category = categories.GeneralCategory

    class Params(base.BaseModel):
        level: Hashable | Sequence[Hashable] | None = Field(None, title=_("Level"))
        drop: bool = Field(False, title=_("Drop"))
        col_level: Hashable = Field(0, title=_("Column level"))
        col_fill: Hashable | None = Field("", title=_("Column fill"))
        # inplace


class RemoveIndexMethod(methods.DatasetMethod):
    # virtual
    icon = iconnames.REMOVE
    description = _(
        "Remove the index and its data completely. "
        "If no index is left, a new default index will be created."
    )
    short_desc = _("Remove")
    obj = pd.DataFrame.reset_index
    category = categories.GeneralCategory

    class Params(base.BaseModel):
        level: Hashable | Sequence[Hashable] | None = Field(None, title=_("Level"))
        drop: bool = Field(True)


class SetIndexMethod(methods.DatasetMethod):
    icon = iconnames.INDEX
    description = _("Set index")
    short_desc = _("Set index")
    obj = pd.DataFrame.set_index
    category = categories.GeneralCategory

    class Params(base.BaseModel):
        keys: list[Hashable] | Hashable = Field(title=_("New indexes"))
        drop: bool = Field(True, title=_("Delete columns to be used as index"))
        append: bool = Field(False, title=_("Append columns to existing index"))
        verify_integrity: bool = Field(False, title=_("Verify integrity"))


class SortValuesMethod(methods.DatasetMethod):
    icon = iconnames.SORT
    description = _("Sorts the dataset according to specific features.")
    short_desc = _("Sort by feature")
    obj = pd.DataFrame.sort_values
    category = categories.GeneralCategory

    class Params(base.BaseModel):
        by: Hashable | list[Hashable] = Field(title=_("Columns"))
        axis: int | str = Field(0, title=_("Axis"), mapping=AXIS_ITEMS)
        ascending: bool = Field(False, title=_("Orientation"), mapping=ORDER_OPTS)
        kind: str = Field("quicksort", title=_("Sort algorithm"), mapping=SORT_ALGO)
        na_position: str = Field("last", title=_("NA position"), mapping=NA_POS)
        ignore_index: bool = Field(False, title=_("Ignore index"))


class SortIndexMethod(methods.DatasetMethod):
    icon = iconnames.SORT
    description = _("Sort dataset based on index.")
    short_desc = _("Sort by index")
    obj = pd.DataFrame.sort_index
    category = categories.GeneralCategory

    class Params(base.BaseModel):
        axis: int | str = Field(0, title=_("Axis"), mapping=AXIS_ITEMS)
        level: Hashable | Sequence[Hashable] | None = Field(None, title=_("Levels"))
        ascending: bool = Field(True, title=_("Orientation"), mapping=ORDER_OPTS)
        kind: str = Field("quicksort", title=_("Sort algorithm"), mapping=SORT_ALGO)
        na_position: str = Field("last", title=_("NA position"), mapping=NA_POS)
        sort_remaining: bool = Field(False, title=_("Sort remaining"))


class ReorderLevelsMethod(methods.DatasetMethod):
    icon = iconnames.SORT
    description = _("Rearrange index levels using input order.")
    short_desc = _("Reorder levels")
    obj = pd.DataFrame.reorder_levels
    category = categories.GeneralCategory

    class Params(base.BaseModel):
        order: list = Field(title=_("New order"))
        axis: int | str = Field(0, title=_("Axis"), mapping=AXIS_ITEMS)


class DropMethod(methods.DatasetMethod):
    icon = iconnames.REMOVE
    description = _("Remove features from dataset")
    short_desc = _("Remove")
    obj = pd.DataFrame.drop
    category = categories.GeneralCategory

    class Params(base.BaseModel):
        labels: list = Field(title=_("Labels"))
        axis: int | str = Field(0, title=_("Axis"), mapping=AXIS_ITEMS)
        errors: str = Field("raise", title=_("Error"), mapping=ERRORS)


class DropDuplicatesMethod(methods.DatasetMethod):
    icon = iconnames.DROP_DUPLICATES
    description = _("Drop rows containing duplicates of selected features.")
    short_desc = _("Drop duplicates")
    obj = pd.DataFrame.drop_duplicates
    category = categories.GeneralCategory

    class Params(base.BaseModel):
        keep: str | bool = Field("first", title=_("Keep"), mapping=DROP_METHODS)
        subset: list | None = Field(None, title=_("Columns"))


class InterpolateMethod(methods.DatasetMethod):
    icon = iconnames.NAN
    description = _("Interpolate NaN values")
    short_desc = _("Interpolate NaN values")
    obj = pd.DataFrame.interpolate
    category = categories.GeneralCategory
    same_shape = True

    class Params(base.BaseModel):
        method: str = Field("linear", title=_("Method"), mapping=INTERPOLATE_METHODS)
        limit: int | None = Field(None, title=_("Limit"))
        limit_direction: str = Field(
            "forward", title=_("Limit direction"), mapping=LIMIT_DIRECTIONS
        )


class ShiftMethod(methods.DatasetMethod):
    icon = iconnames.SHIFT
    description = _("Shift values by a user specified offset.")
    short_desc = _("Shift values")
    obj = pd.DataFrame.shift
    category = categories.GeneralCategory
    same_shape = True

    class Params(base.BaseModel):
        periods: int = Field(1, title=_("Shift by"))
        fill_value: Any = Field(None, title=_("Fill value"), mapping=FILL_OPTS)


class ClipMethod(methods.DatasetMethod):
    icon = iconnames.CLIP
    description = _("Trim values above / below a specified threshold.")
    short_desc = _("Trim values")
    obj = pd.DataFrame.clip
    category = categories.GeneralCategory
    same_shape = True

    class Params(base.BaseModel):
        lower: float | None = Field(None, title=_("Lower Threshold"))
        upper: float | None = Field(None, title=_("Upper Threshold"))


class ReplaceMethod(methods.DatasetMethod):
    icon = iconnames.RENAME
    description = _("Replace specific values with new ones")
    short_desc = _("Replace values")
    obj = pd.DataFrame.replace
    category = categories.StringCategory
    same_shape = True

    class Params(base.BaseModel):
        to_replace: Any = Field(title=_("Old value"))
        value: Any = Field(title=_("New value"))


class DiffMethod(methods.DatasetMethod):
    icon = iconnames.DIFF
    description = _("Calculates differences based on row / column with user-specified offset.")
    short_desc = _("Difference to offset")
    obj = pd.DataFrame.diff
    category = categories.GeneralCategory
    same_shape = True

    class Params(base.BaseModel):
        periods: int = Field(1, title=_("Offset"))
        axis: int | str = Field(0, title=_("Axis"), mapping=AXIS_ITEMS)


class ReindexMethod(methods.DatasetMethod):
    icon = iconnames.INDEX
    description = _("Reindex")
    short_desc = _("Reindex")
    obj = pd.DataFrame.reindex
    category = categories.GeneralCategory

    class Params(base.BaseModel):
        labels: list | None = Field(None, title=_("Labels"))
        axis: int | str = Field(0, title=_("Axis"), mapping=AXIS_ITEMS)
        method: str | None = Field(None, title=_("Method"), mapping=REINDEX_METHODS)


class RenameMethod(methods.DatasetMethod):
    icon = iconnames.RENAME
    description = _("Alter axes labels.")
    short_desc = _("Rename")
    obj = pd.DataFrame.rename
    category = categories.GeneralCategory

    class Params(base.BaseModel):
        mapper: dict | Callable = Field(title=_("Labels"))
        axis: int | str = Field(0, title=_("Axis"), mapping=AXIS_ITEMS)


class DropNaMethod(methods.DatasetMethod):
    icon = iconnames.NAN
    description = _("Remove NaN rows")
    short_desc = _("Remove NaN rows")
    obj = pd.DataFrame.dropna
    category = categories.NanCategory

    class Params(base.BaseModel):
        how: str = Field("all", title=_("Drop if"), mapping=NAN_CHOICES)
        subset: list | None = Field(None, title=_("Labels along other axis to consider"))
        axis: int | str = Field(0, title=_("Axis"), mapping=AXIS_ITEMS)


class FillNaMethod(methods.DatasetMethod):
    icon = iconnames.NAN
    description = _("Fill NaN values")
    short_desc = _("Fill NaN values")
    obj = pd.DataFrame.fillna
    category = categories.NanCategory
    same_shape = True

    class Params(base.BaseModel):
        method: str | None = Field("ffill", title=_("Mode"), mapping=FILL_MODES)
        axis: int | str = Field(0, title=_("Axis"), mapping=AXIS_ITEMS)
        value: str | float | None = Field(None, title=_("Value"))

    params: Params

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # pandas >= 3 removed fillna(method=...), dispatch to ffill / bfill instead.
        if self.params.method in ("ffill", "bfill"):
            self.obj = getattr(pd.DataFrame, self.params.method)

    def get_nondefault_params(self) -> dict[str, Any]:
        params = super().get_nondefault_params()
        params.pop("method", None)
        if self.params.method in ("ffill", "bfill"):
            params.pop("value", None)
        return params


class ReplaceWithNaMethod(methods.DatasetMethod):
    icon = iconnames.NAN
    description = _("Replace with NaN")
    short_desc = _("Replace with NaN")
    obj = pd.DataFrame.replace
    category = categories.NanCategory
    same_shape = True

    class Params(base.BaseModel):
        to_replace: Any = Field("0", title=_("To replace"))
        value: Any = Field(np.nan, fixed=True)


class StackMethod(methods.DatasetMethod):
    # TODO: for actions:
    # def is_visible(self):
    #     is_multi = isinstance(self.model.ds.columns, pd.MultiIndex)
    #     return len(self.indexes) > 0 and is_multi

    icon = iconnames.PLOT
    description = _("Stack")
    short_desc = _("Stack")
    obj = pd.DataFrame.stack
    category = categories.ReshapeCategory

    class Params(base.BaseModel):
        # level: Union[int, str] = Field(-1, title=_("Level"))
        dropna: bool = Field(True, title=_("Drop NA"))


class TransposeMethod(methods.DatasetMethod):
    icon = iconnames.TRANSPOSE
    description = _("Transpose")
    short_desc = _("Transpose")
    obj = pd.DataFrame.transpose
    category = categories.ReshapeCategory
    # TODO: set copy param?


class AsFreqMethod(methods.DatasetMethod):
    icon = iconnames.TRANSPOSE
    description = _("Resample dataset")
    short_desc = _("Resample dataset")
    obj = pd.DataFrame.asfreq
    category = categories.GeneralCategory

    class Params(base.BaseModel):
        freq: str = Field(title=_("Frequency"))


class MeltMethod(methods.DatasetMethod):
    icon = iconnames.MELT
    description = _("Melt")
    short_desc = _("Melt")
    obj = pd.DataFrame.melt
    category = categories.ReshapeCategory

    class Params(base.BaseModel):
        id_vars: list | None = Field(None, title=_("Id variables"))
        value_vars: list | None = Field(None, title=_("Value variables"))


class PivotMethod(methods.DatasetMethod):
    icon = iconnames.PIVOT
    description = _("Return reshaped DataFrame organized by given index / column values.")
    short_desc = _("Pivot dataframe")
    obj = pd.DataFrame.pivot
    category = categories.ReshapeCategory

    class Params(base.BaseModel):
        columns: Any = Field(title=_("Columns"))
        index: Any = Field(title=_("Index"))
        values: Any = Field(title=_("Values"))


class PivotTableMethod(methods.DatasetMethod):
    icon = iconnames.PIVOT
    description = _("Create a spreadsheet-style pivot table as a DataFrame.")
    short_desc = _("Pivot table")
    obj = pd.DataFrame.pivot_table
    category = categories.ReshapeCategory

    class Params(base.BaseModel):
        index: Any = Field(title=_("Index"))
        columns: Any = Field(title=_("Columns"))
        values: Any = Field(None, title=_("Values"))
        aggfunc: str | Callable = Field(
            "mean", title=_("Aggregation function"), mapping=PIVOT_METHODS
        )
        margins: bool = Field(False, title=_("Margins"))
        dropna: bool = Field(True, title=_("Drop NA"))
        margins_name: str = Field("All", title=_("Margins name"))
        observed: bool = Field(False, title=_("Only show observed values"))


class SampleMethod(methods.DatasetMethod):
    icon = iconnames.DIFF
    description = _("Take random sample")
    short_desc = _("Take random sample")
    obj = pd.DataFrame.sample
    category = categories.FilterCategory

    class Params(base.BaseModel):
        n: int = Field(2, title=_("Sample size"), ge=1)
        frac: float | None = Field(None, title=_("Fraction"), ge=0, le=1)  # unit="%"
        random_state: int | None = Field(None, title=_("True random"), mapping=RANDOM_STATE)
        axis: int | str = Field(0, title=_("Axis"), mapping=AXIS_ITEMS)


class NSmallestMethod(methods.DatasetMethod):
    icon = iconnames.DIFF
    description = _("Filter smallest")
    short_desc = _("Filter smallest")
    obj = pd.DataFrame.nsmallest
    comment = _("Get the rows of a DataFrame sorted by the n smallest values of columns.")
    category = categories.FilterCategory

    class Params(base.BaseModel):
        n: int = Field(1, title=_("Amount"), ge=1)
        columns: str | list = Field(title=_("Columns"))
        keep: str = Field("first", title=_("Keep"), mapping=KEEP_OPTS)


class NLargestMethod(methods.DatasetMethod):
    icon = iconnames.DIFF
    description = _("Filter largest")
    short_desc = _("Filter largest")
    obj = pd.DataFrame.nlargest
    comment = _("Get the rows of a DataFrame sorted by the n largest values of columns.")
    category = categories.FilterCategory

    class Params(base.BaseModel):
        n: int = Field(1, title=_("Amount"), ge=1)
        columns: str | list = Field(title=_("Columns"))
        keep: str = Field("first", title=_("Keep"), mapping=KEEP_OPTS)


class CorrMethod(methods.DatasetMethod):
    icon = iconnames.CORRELATIONS
    description = _("Correlations")
    short_desc = _("Correlations")
    obj = pd.DataFrame.corr
    comment = _("Provides correlation of different types. (Spearman, Kendall, Pearson)")
    category = categories.StatsCategory

    class Params(base.BaseModel):
        method: str = Field("pearson", title=_("Method"), mapping=CORRELATION_TYPES)


class RankMethod(methods.DatasetMethod):
    icon = iconnames.STATS
    description = _("Ranks")
    short_desc = _("Ranks")
    obj = pd.DataFrame.rank
    category = categories.StatsCategory
    same_shape = True

    class Params(base.BaseModel):
        method: str = Field("average", title=_("Method"), mapping=RANK_METHODS)
        na_option: str = Field("keep", title=_("NaN handling"), mapping=NA_OPTIONS)
        numeric_only: bool = Field(False, title=_("Exclude non-numeric data"))
        ascending: bool = Field(True, title=_("Ascending order"))
        pct: bool = Field(False, title=_("As percentage"))


class ModeMethod(methods.DatasetMethod):
    icon = iconnames.STATS
    description = _("Modes")
    short_desc = _("Modes")
    obj = pd.DataFrame.mode
    comment = _(
        "Gets the mode(s) of each element along the axis selected."
        " Adds a row for each mode per label, fills in gaps with nan."
    )
    category = categories.StatsCategory
    same_shape = True

    class Params(base.BaseModel):
        axis: int | str = Field(0, title=_("Axis"), mapping=AXIS_ITEMS)
        numeric_only: bool = Field(False, title=_("Only apply to numeric columns"))
        dropna: bool = Field(True, title=_("Do not consider counts of NaN/NaT"))


class DescribeMethod(methods.DatasetMethod):
    description = _("Descriptive statistics")
    short_desc = _("Descriptive statistics")
    obj = pd.DataFrame.describe
    icon = iconnames.STATS
    category = categories.StatsCategory


class VarMethod(methods.DatasetMethod):
    description = _("Variances")
    short_desc = _("Variances")
    obj = pd.DataFrame.var
    icon = iconnames.STATS
    category = categories.StatsCategory
    # same_shape = True

    class Params(base.BaseModel):
        axis: int | str = Field(0, title=_("Axis"), mapping=AXIS_ITEMS)
        skipna: bool = Field(True, title=_("Do not consider counts of NaN/NaT"))
        ddof: int = Field(1, title=_("Delta Degrees of Freedom"))
        numeric_only: bool | None = Field(None, title=_("Include only float, int, boolean columns"))


class CovMethod(methods.DatasetMethod):
    icon = iconnames.STATS
    description = _("Covariances")
    short_desc = _("Covariances")
    obj = pd.DataFrame.cov
    category = categories.StatsCategory
    # same_shape = True

    class Params(base.BaseModel):
        min_periods: int | None = Field(None, title=_("Minimum number of observations"))


class GroupByMethod(methods.DatasetMethod):
    icon = iconnames.GROUPBY
    description = _("Group dataframe based on selected features.")
    short_desc = _("Group by")
    obj = pd.DataFrame.groupby
    category = categories.GeneralCategory

    class Params(base.BaseModel):
        by: dict | Callable | str | list[str] = Field(title=_("By"))
        observed: bool = Field(False, title="Only show observed values")


class ResampleMethod(methods.DatasetMethod):
    icon = iconnames.TIME
    description = _("Resample dataframe to groups.")
    short_desc = _("Resample")
    obj = pd.DataFrame.resample
    category = categories.GeneralCategory

    class Params(base.BaseModel):
        rule: str = Field("1s", title=_("Resampling interval"))
        closed: str | None = Field(None, title=_("Side with closed interval"), mapping=SIDE_OPTS)
        label: str | None = Field(None, title=_("Label bucket with"), mapping=SIDE_OPTS)


class AsTypeMethod(methods.DatasetMethod):
    icon = iconnames.DATASET
    description = _("Convert data type.")
    short_desc = _("Convert data type")
    obj = pd.DataFrame.astype

    class Params(base.BaseModel):
        dtype: str = Field(title=_("New data type"))


# class Renamemethod(methods.DatasetMethod):

#     icon = iconnames.RENAME
#     description = _("Rename the dataset.")
#     short_desc = _("Rename dataset")
#     comment = _("{i} will get replaced with count, "
#                 "{name} with previous name")

#     class Params(base.BaseModel):
#         new_name: str = Field(title=_("New name"), min_length=1)

#     def apply_method(self, ds):
#         ds.set_title(self.params.new_name)
#         return ds

# class RollingMethod(methods.DatasetMethod):

#     icon = iconnames.ROLLING
#     description = _("Provides rolling window calculations")
#     short_desc = _("Rolling window operations")
#     obj = pd.DataFrame.rolling

#     class Params(base.BaseModel):
#         win_type: str | None = Field(title=_("Window type"), mapping=WIN_TYPES)
#         window: int = Field(5, title=_("Window size"), min_val=2)
#         method = Field(title=_("Method"), METHODS)
#         min_periods: int = Field(1,
#             title=_("Minimum amount of periods."), min_val=1)
#         axis: Union[int, str] = Field(0, title=_("Axis"), mapping=AXIS_ITEMS)
#         center: bool = Field(False,
# title=_("Set the labels at the center of the window"))

#     def apply_method(self, ds):
#         name = self.obj.__name__
#         keyword_args = self.params.to_dict()
#         method = keyword_args.pop("method")
#         rolling = getattr(ds, name)(**keyword_args)
#         df = getattr(rolling, method)()
#         ds = dataset.DataSet(data=df,
#                              inherit_from=ds,
#                              name=f"{ds.title} {name} {method}")
#         ds.log(f"|ds| = |ds|.{name}(|KWARGS|).{method}()",
#                description=f"{name.title()} {method}",
#                kwargs=keyword_args)
#         return ds


# class ExpandingMethod(RollingMethod):

#     icon = iconnames.ROLLING
#     description = _("Provides expanding window calculations")
#     short_desc = _("Expanding window operations")
#     obj = pd.DataFrame.expanding

#     class Params(base.BaseModel):
#         method = Field(title=_("Method"), METHODS)
#         min_periods: int = Field(1,
#             title=_("Minimum amount of periods."), min_val=1)
#         axis: Union[int, str] = Field(0, title=_("Axis"), mapping=AXIS_ITEMS)
#         center: bool = Field(False,
# title=_("Set the labels at the center of the window"))

if __name__ == "__main__":
    from datacook.core import dataset

    df = dataset.DataSet({"A": ["a", "b", "c", "a"]})
    df["B"] = df["A"].astype("category")
    test1 = AddPrefixMethod(prefix="test_")
    test1.apply_method(df)
    test2 = AddSuffixMethod(suffix="_test")
    test2.apply_method(df)
    # test3 = Renamemethods.DatasetMethod(new_name="testus")
    # test3.apply_method(df)
    # test4 = RollingMethod()
    # test4.apply_method(df)
    # test5 = ExpandingMethod()
    # test5.apply_method(df)
    # test6 = GetDummiesMethod()
    # test6.apply_method(df)
    # test7 = ResetIndexMethod()
    # test7.apply_method(df)
