from __future__ import annotations

from collections.abc import Hashable
from typing import Any

import pandas as pd
from pydantic import Field

from datacook.constants import iconnames
from datacook.core import categories
from datacook.core.application import _
from datacook.methods import base, methods


CORRELATION_TYPES = [
    ("pearson", "Pearson"),
    ("spearman", "Spearman"),
    ("kendall", "Kendall"),
]


MERGE_OPTS = [
    ("inner", _("Inner"), iconnames.JOIN_INNER),
    ("outer", _("Outer"), iconnames.JOIN_ALL),
    ("left", _("Left"), iconnames.JOIN_LEFT),
    ("right", _("Right"), iconnames.JOIN_RIGHT),
]


class CorrWithMethod(methods.DatasetMethod):
    icon = iconnames.CORRELATIONS
    description = _("Compute pairwise correlation.")
    short_desc = _("Correlations")
    obj = pd.DataFrame.corrwith
    comment = _("Provides correlation of different types. (Spearman, Kendall, Pearson)")
    category = categories.StatsCategory
    result = "Series"

    class Params(base.BaseModel):
        other: Any = Field(title=_("Other"))
        method: str = Field("pearson", title=_("Method"), mapping=CORRELATION_TYPES)
        drop: bool = Field(False, title=_("Drop missing indices"))


class MergeMethod(methods.DatasetMethod):
    icon = iconnames.MERGE
    description = _("Merge two dataframes")
    short_desc = _("Merge")
    obj = pd.DataFrame.merge
    category = categories.GeneralCategory

    class Params(base.BaseModel):
        right: Any = Field(title=_("Other"))
        how: str = Field("inner", title=_("Method"), mapping=MERGE_OPTS)
        left_on: Hashable | list[Hashable] = Field(None, title=_("Column no 1 for joining"))
        right_on: Hashable | list[Hashable] = Field(None, title=_("Column no 2 for joining"))
        left_index: bool = Field(False, title=_("Left index"))
        right_index: bool = Field(False, title=_("Right index"))
        sort: bool = Field(False, title=_("Sort"))
        indicator: bool = Field(False, title=_("Indicator"))


# class AppendMethod(methods.DatasetMethod):
#     icon = iconnames.MERGE
#     description = _("Append rows of another dataframe")
#     short_desc = _("Append")
#     obj = pd.DataFrame.append
#     category = categories.GeneralCategory

#     class Params(base.BaseModel):
#         other: Any = Field(title=_("Other"))
#         ignore_index: bool = Field(False, title=_("Ignore index"))
#         sort: bool = Field(False, title=_("Sort"))
