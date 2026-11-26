from __future__ import annotations

from collections.abc import Callable, Hashable

import pandas as pd
from pydantic import Field

from datacook.constants import iconnames
from datacook.core.application import _
from datacook.methods import base, methods


class GroupByAndFilterMethod(methods.BaseMethod):
    icon = iconnames.EXTRACT
    description = _("Create a new single dataset containing selected groups.")
    short_desc = _("Filter dataset")
    obj = pd.api.typing.DataFrameGroupBy.filter

    class Params(base.BaseModel):
        func: Callable = Field(title=_("Function"))
        dropna: bool = Field(True, title=_("Drop NA"))

    def apply_method(self, groupby_obj):
        keyword_args = self.params.to_dict()
        fn_kwargs = keyword_args.copy()
        fn_kwargs["func"] = eval(fn_kwargs["func"])
        ds = groupby_obj.filter(**fn_kwargs)
        ds.log(
            f"|ds| = {groupby_obj.grouper_log}.filter({keyword_args})",
            description="Filter groups",
        )


class GroupByAndGetGroupMethod(methods.BaseMethod):
    icon = iconnames.STATS
    description = _("Get group.")
    short_desc = _("Get group")
    obj = pd.api.typing.DataFrameGroupBy.get_group

    class Params(base.BaseModel):
        name: Hashable = Field(title=_("Group name"))


class GroupByAndTransformMethod(methods.BaseMethod):
    icon = iconnames.TRANSFORMER
    description = _("Transform.")
    short_desc = _("Transform")
    obj = pd.api.typing.DataFrameGroupBy.transform

    class Params(base.BaseModel):
        func: Callable | str = Field(title=_("Function"))


if __name__ == "__main__":
    from datacook.core import dataset

    df = dataset.DataSet({"A": ["a", "b", "c", "a"]})
    df["B"] = df["A"].astype("category")
