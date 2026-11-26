from __future__ import annotations

from collections.abc import Hashable
import logging

import pandas as pd
import pandastools  # pylint: disable=unused-import  # noqa: F401
from pydantic import Field

from datacook.constants import iconnames
from datacook.core import categories
from datacook.core.application import _
from datacook.methods import base, methods


logger = logging.getLogger(__name__)


class ToleranceBandMethod(methods.DatasetPtMethod):
    icon = iconnames.TOLERANCE_BANDS
    category = categories.StatsCategory
    description = _("Create a dataset with values for tolerance bands.")
    short_desc = _("Tolerance bands")
    obj = pd.Series.pt.tolerance_bands

    class Params(base.BaseModel):
        window: str | float = Field(title=_("Window size"), ge=2, le=1000)
        pct: float = Field(title=_("Maximum difference"), ge=0, le=1)


class MergeColumnsMethod(methods.DatasetPtMethod):
    icon = iconnames.MERGE
    description = _("Merge column contents")
    short_desc = _("Merge")
    obj = pd.DataFrame.pt.merge_columns
    add_feat = True

    class Params(base.BaseModel):
        columns: list[Hashable] = Field(title=_("Columns"))
        divider: str = Field(title=_("Divider"), default=" ")


class DuplicateFeaturesMethod(methods.DatasetPtMethod):
    icon = iconnames.CREATE_COPY
    description = _("Create a copy of the features")
    short_desc = _("Duplicate features")
    add_feat = True
    obj = pd.DataFrame.pt.duplicate_features

    class Params(base.BaseModel):
        columns: list[Hashable] = Field(title=_("Columns"))


class SplitMethod(methods.DatasetPtMethod):
    icon = iconnames.SPLIT
    description = _("Add split info")
    short_desc = _("Add split info")
    add_feat = True
    obj = pd.DataFrame.pt.split

    class Params(base.BaseModel):
        thresh: float = Field(title=_("Threshold"))
        colname: Hashable = Field(title=_("Column name"))
        extra_rows: int = Field(0, title=_("Extra rows"))


class UniquifyColumnsMethod(methods.DatasetPtMethod):
    icon = iconnames.SPLIT
    description = _("Uniquify columns")
    short_desc = _("Uniquify columns")
    obj = pd.DataFrame.pt.uniquify_columns


if __name__ == "__main__":
    from datacook.core import dataset

    df = dataset.DataSet({"A": [1, 2, 3, 4, 5, 6]})
    test1 = ToleranceBandMethod(window=5, pct=0.1)
    test1.apply_method(df)
