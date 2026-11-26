from __future__ import annotations

import functools
import logging

import openml.datasets
import pandas as pd

from processanalyzer.constants import iconnames
from processanalyzer.core import dataset, threads
from processanalyzer.gui.dialogs import tabledialog
from processanalyzer.plugintypes import readerplugin

logger = logging.getLogger(__name__)


class OpenMLReader(readerplugin.ReaderPlugin):
    menu_label = "OpenML dataset"
    plugin_id = "reader.openml"
    icon = iconnames.ML
    context_label = "OpenML dataset importer"

    def read(self, path=None):
        worker = threads.Worker(openml.datasets.list_datasets, output_format="dataframe")
        worker.signals.result.connect(self.show_dialog)
        threads.pool.start(worker)

    def show_dialog(self, list_df):
        dialog = tabledialog.TableDialog(df=list_df, title="OpenML importer")
        dialog.selected_indexes.connect(self.read_async)
        dialog.show_blocking()

    def read_async(self, indexes):
        ids = [x.data() for x in indexes if x.column() == 0]
        gen = functools.partial(yield_datasets, ids)
        self.yield_async(gen)


def yield_datasets(ids):
    for identifier in ids:
        data = openml.datasets.get_dataset(identifier)
        X, y, __, ___ = data.get_data(dataset_format="dataframe")
        ds = dataset.DataSet(data=pd.concat([X, y], axis=1), name=data.name)
        ds.log(
            "data = openml.datasets.get_dataset(|ORIGIN|)",
            "X, y, __, ___ = data.get_data(dataset_format='dataframe')",
            "|ds| = pandas.concat([X, y], axis=1)",
            imports=["openml.datasets", "pandas"],
            operation="import",
            origin=identifier,
            description="Import from OpenML",
        )
        yield ds
