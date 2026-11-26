from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

# import numpy as np
import pandas as pd
import pandastools  # noqa: F401

from datacook.core import history, historyitemmixin


if TYPE_CHECKING:
    from collections.abc import Iterable

    import numpy as np


logger = logging.getLogger(__name__)


class DataSet(historyitemmixin.HistoryItemMixin):
    # normal properties
    item_name = "ds"
    obj = pd.DataFrame

    def __init__(
        self,
        data: pd.DataFrame | Iterable | dict | np.ndarray | None = None,
        index=None,
        columns=None,
        history: history.History | None = None,
        comment: str = "",
        name: str | None = None,
        inherit_from: historyitemmixin.HistoryItemMixin | None = None,
        **kwargs,
    ):
        super().__init__(name=name, history=history, comment=comment, inherit_from=inherit_from)
        if isinstance(data, DataSet):
            data = data.instance
        self.instance = pd.DataFrame(data, index=index, columns=columns).copy()

    def __getitem__(self, index):
        return self.instance[index]

    def __contains__(self, item):
        return item in self.instance

    def __setitem__(self, index, val):
        self.instance[index] = val

    def __getattr__(self, name):
        # return getattr(self.instance, name)
        attr = getattr(self.instance, name)

        class Wrapper:
            def __getitem__(_self, index):  # noqa: N805 (closure over the outer self)
                result = attr.__getitem__(index)
                if type(result) is self.obj:
                    result = type(self)(result, inherit_from=self)
                    logger.debug("converting %s to %s", self.obj.__name__, type(self).__name__)
                return result

            def __call__(_self, *args, **kwargs):  # noqa: N805
                result = attr.__call__(*args, **kwargs)
                if type(result) is self.obj:
                    result = type(self)(result, inherit_from=self)
                    logger.debug("converting %s to %s", self.obj.__name__, type(self).__name__)
                return result

        if callable(attr):
            return Wrapper()
        return attr

    def __len__(self):
        return len(self.instance)

    def __repr__(self):
        text = f"{type(self).__name__} {self.title}\n{self.instance!r}"
        if self.history is not None:
            text += f"\n\nCode:\n{self.history.as_code()}"
        return text

    def set_data(self, data: pd.DataFrame):
        self.instance = data

    @property
    def index(self):
        return self.instance.index

    @index.setter
    def index(self, val):
        self.instance.index = val

    @property
    def columns(self):
        return self.instance.columns

    @columns.setter
    def columns(self, val):
        self.instance.columns = val

    def groupby(self, *args, **kwargs):
        grouped = self.instance.groupby(*args, **kwargs)
        return Wrapper(grouped, self)

    def resample(self, *args, **kwargs):
        resampled = self.instance.resample(*args, **kwargs)
        return Wrapper(resampled, self)

    def get_metadata(self) -> dict[str, Any]:
        return dict(rows=self.shape[0], columns=self.shape[1])

    def to_pandas_df(self) -> pd.DataFrame:
        return self.instance

    # def pivot_table(self, *args, **kwargs):
    #     df = super().pivot_table(*args, **kwargs)
    #     return DataSet(df, name=self.title, inherit_from=self)

    # def convert_dtypes(self, *args, **kwargs):
    #     df = super().convert_dtypes(*args, **kwargs)
    #     return DataSet(df, name=self.title, inherit_from=self)

    # def describe(self, *args, **kwargs):
    #     df = super().describe(*args, **kwargs)
    #     return DataSet(df, name=self.title, inherit_from=self)

    # def corrwith(self, *args, **kwargs):
    #     df = super().corrwith(*args, **kwargs)
    #     return DataSet(df, name=self.title, inherit_from=self)


class Wrapper:
    def __init__(self, instance, ds):
        self.instance = instance
        self.obj = ds

    # def get_group(self, group):
    #     return DataSet(self.groupby.get_group(group),
    #                    inherit_from=self.obj)

    def __len__(self):
        return len(self.instance)

    def __contains__(self, key):
        return key in self.instance

    def __getitem__(self, index):
        return self.instance[index]

    def __setitem__(self, index, val):
        self.instance[index] = val

    def __getattr__(self, name):
        attr = getattr(self.instance, name)
        if callable(attr):

            def wrapper(*args, **kwargs):
                result = attr(*args, **kwargs)
                if isinstance(result, pd.DataFrame):
                    result = DataSet(result, inherit_from=self.obj)
                return result

            return wrapper
        return attr


if __name__ == "__main__":
    ds1 = DataSet(name="Test")
    ds1.set_comment("testcomment")
