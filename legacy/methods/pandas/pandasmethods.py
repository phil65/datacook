from __future__ import annotations

from collections.abc import Callable, Hashable
from typing import Any

import pandas as pd
from pydantic import Field

from datacook.constants import iconnames
from datacook.core import dataset
from datacook.core.application import _
from datacook.methods import base, methods
from datacook.util import helpers


MERGE_METHODS = {
    "inner": _("Inner"),
    "outer": _("Outer"),
    "left": _("Left"),
    "right": _("Right"),
}

CORRELATION_TYPES = {
    "spearman": "Spearman",
    "kendall": "Kendall",
    "pearson": "Pearson",
}

JOINS = {
    "outer": _("Outer"),
    "inner": _("Inner"),
}

AXIS_ITEMS = {0, _("Index"), 1, _("Columns")}


class PandasMethod(methods.BaseMethod):
    short_desc = "UNDEFINED"

    def apply_method(self, ds):
        keyword_args = self.get_nondefault_params()
        method_name = self.method_name
        df = getattr(ds, method_name)(**keyword_args)
        ds = dataset.DataSet(df, inherit_from=ds)
        ds.log(
            f"|ds| = pandas.{method_name}(|KWARGS|)",
            description=self.short_desc,
            kwargs=keyword_args,
            imports=["pandas"],
        )
        return ds

    def log_template(self):
        method_name = self.method_name
        return f"|ds| = pandas.{method_name}(|KWARGS|)"

    def preview_log(self, columns=None):
        text = self.log_template()
        text = text.replace("|ds|", f"ds{columns}") if columns else text.replace("|ds|", "ds")
        dct = self.params.to_dict()
        text = text.replace("|KWARGS|", helpers.format_kwargs(dct))
        return text.replace("|OPTKWARGS|", helpers.format_kwargs(dct, prepend_comma=True))


class GetDummiesMethod(PandasMethod):
    icon = iconnames.DIFF
    description = _("Apply one-hot encoding to categorical features.")
    short_desc = _("One-Hot encode")
    obj = pd.get_dummies

    class Params(base.BaseModel):
        # data = Field(label="Data")
        dummy_na: bool = Field(title=_("Feature for NaN values"))
        drop_first: bool = Field(title=_("Remove first level"))

    def apply_method(self, ds: dataset.DataSet):
        keyword_args = self.get_nondefault_params()
        ds = dataset.DataSet(pd.get_dummies(ds.instance, **keyword_args), inherit_from=ds)
        ds.log(
            "|ds| = pandas.get_dummies(|ds||OPTKWARGS|)",
            description="One-hot encode",
            kwargs=keyword_args,
            imports=["pandas"],
        )
        return ds


class ConcatMethod(PandasMethod):
    icon = iconnames.MERGE
    description = _("Stack several dataframes into one")
    short_desc = _("Concat")
    obj = pd.concat

    class Params(base.BaseModel):
        join: str = Field("outer", title=_("Method"), mapping=JOINS)
        axis: int | str = Field(0, title=_("Axis"), mapping=AXIS_ITEMS)
        sort: bool = Field(False, title=_("Sort"))
        ignore_index: bool = Field(False, title=_("Ignore index"))
        keys: list[Hashable] | None = Field(None, title=_("Keys for MultiIndex"))

    def apply_method(self, dfs: list):  # ty: ignore[lost-keyword-for-regular-parameter]
        keyword_args = self.get_nondefault_params()
        ds = dataset.DataSet(pd.concat([ds.instance for ds in dfs], **keyword_args))
        ds.log(
            "|ds| = pandas.concat(|CHILD_NAMES||OPTKWARGS|)",
            imports=["pandas"],
            description=f"Merge {len(dfs)} datasets",
            name=f"{len(dfs)} merged datasets",
            operation="merge",
            children=[i.history for i in dfs],
            kwargs=keyword_args,
        )
        ds.set_name(f"{len(dfs)} merged datasets")
        return ds


class MergeMethod(PandasMethod):
    icon = iconnames.MERGE
    description = _("Stack several dataframes into one")
    short_desc = _("Concat")
    obj = pd.merge

    class Params(base.BaseModel):
        how: str = Field("inner", title=_("Method"), mapping=MERGE_METHODS)
        left_index: bool = Field(False, title=_("Left: Join on index"))
        left_on: Hashable | list[Hashable] | None = Field(None, title=_("Left join column"))
        right_index: bool = Field(False, title=_("Right: Join on index"))
        right_on: Hashable | list[Hashable] | None = Field(None, title=_("Right join column"))
        indicator: bool = Field(True, title=_("Add indicator column"))

    def apply_method(  # ty: ignore[incompatible-method-override]
        self, left: pd.DataFrame, right: pd.DataFrame
    ):
        keyword_args = self.get_nondefault_params()
        ds = dataset.DataSet(pd.merge(left, right, **keyword_args))
        ds.log(
            "|ds| = pandas.merge(|CHILD_NAME_1|, |CHILD_NAME_2||OPTKWARGS|)",
            imports=["pandas"],
            description="Merge with dataset",
            name="2 merged datasets",
            operation="merge",
            kwargs=keyword_args,
            children=[left.history, right.history],
        )
        ds.set_name("2 merged datasets")
        return ds


class PivotTableMethod(PandasMethod):
    icon = iconnames.PIVOT
    description = _("Create pivot table")
    short_desc = _("Pivot table")
    obj = pd.pivot_table

    class Params(base.BaseModel):
        data: Any = Field(title=_("DataFrame"))
        index: Any = Field(None, title=_("Index"))
        columns: Any = Field(None, title=_("Columns"))
        values: Any = Field(None, title=_("Values"))
        aggfunc: str | Callable = Field("mean", title=_("Aggregation function"))
        margins: bool = Field(title=_("Margins"))
        observed: bool = Field(False, title=_("Only show observed values for categorical groupers"))

    def apply_method(self, ds):
        keyword_args = self.get_nondefault_params()
        ds = pd.pivot_table(ds, **keyword_args)
        ds.log(
            "|ds| = pandas.pivot_table(|ds||OPTKWARGS|)",
            description="Pivot dataset",
            name=ds.title,
            imports=["pandas"],
            kwargs=keyword_args,
        )
        return ds


class CrossTabMethod(PandasMethod):
    icon = iconnames.PIVOT
    description = _("Compute a simple cross tabulation of two (or more) factors. ")
    short_desc = _("Create crosstab")
    obj = pd.crosstab

    class Params(base.BaseModel):
        index: Any = Field(title=_("Index"))
        columns: Any = Field(title=_("Columns"))
        values: Any = Field(None, title=_("Values"))
        aggfunc: str | Callable | None = Field(None, title=_("Aggregation function"))
        margins: bool = Field(False, title=_("Margins"))
        dropna: bool = Field(True, title=_("Drop NA"))
        margins_name: str = Field("All", title=_("Margins name"))

    def apply_method(self, ds, col_1, col_2):  # ty: ignore[incompatible-method-override]
        keyword_args = self.params.to_dict()
        ds = pd.crosstab(ds, **keyword_args)
        ds.log(
            f"|ds| = pandas.crosstab(|ds|{[col_1]}, |ds|{[col_2]}|OPTKWARGS|)",
            description=f"Crosstab {col_1} vs {col_2}",
            name=ds.title,
            kwargs=keyword_args,
            imports=["pandas"],
        )
        return ds


class CutMethod(methods.BaseMethod):
    icon = iconnames.BIN
    description = _("Bin values into discrete intervals")
    short_desc = _("Bin values")
    obj = pd.cut
    add_feat = True

    class Params(base.BaseModel):
        bins: int | list[float] = Field(title=_("Bins"))
        right: bool = Field(True, title=_("Bins include rightmost edge"))
        include_lowest: bool = Field(True, title=_("First interval left-inclusive"))
        precision: int = Field(3, title=_("Precision"), ge=0)


if __name__ == "__main__":
    df = dataset.DataSet({"A": ["a", "b", "c", "a"]})
    df2 = df.copy()
    df["B"] = df["A"].astype("category")
    test1 = ConcatMethod()
    test1.apply_method([df, df2])
    test2 = MergeMethod()
    test2.apply_method(df.instance, df2.instance)
