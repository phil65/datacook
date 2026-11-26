"""Map evaluated objects back to the history item class that wraps them."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd


if TYPE_CHECKING:
    from datacook.core.dataset import DataSet


def get_class_for_instance(instance: Any) -> type[DataSet]:
    """Return the history item class for an evaluated object.

    Only DataFrames (-> `DataSet`) are supported. The old plugin-based lookup of
    estimator classes lives in `legacy/core/appmanager.py`.

    Raises:
        TypeError: no history item class wraps objects of this type.
    """
    if isinstance(instance, pd.DataFrame):
        from datacook.core import dataset

        return dataset.DataSet
    msg = f"No history item class for {type(instance).__name__}"
    raise TypeError(msg)
