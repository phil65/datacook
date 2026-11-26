from __future__ import annotations

import functools
import warnings

import seaborn

from processanalyzer.constants import iconnames
from processanalyzer.core import dataset, threads
from processanalyzer.gui.dialogs import tabledialog
from processanalyzer.plugintypes import readerplugin


class SeabornDataSetReader(readerplugin.ReaderPlugin):
    menu_label = "Seaborn dataset"
    plugin_id = "reader.seaborn.datasets"
    icon = iconnames.DATABASE_SEARCH
    context_label = "Seaborn dataset reader"

    def read(self, path=None):
        worker = threads.Worker(self.return_dataset_table)
        worker.signals.result.connect(self.show_dialog)
        threads.pool.start(worker)

    @classmethod
    def return_dataset_table(cls):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return seaborn.get_dataset_names()

    def show_dialog(self, ds_names):
        ds = dataset.DataSet(data=ds_names, columns=["Name"])
        dialog = tabledialog.TableDialog(df=ds, title=self.menu_label)
        dialog.selected_indexes.connect(self.read_async)
        dialog.show_blocking()

    def read_async(self, indexes):
        selected = [x.data() for x in indexes if x.column() == 0]
        gen = functools.partial(yield_datasets, selected)
        self.yield_async(gen)


def yield_datasets(names):
    for name in names:
        ds = dataset.DataSet(data=seaborn.load_dataset(name), name=name)
        ds.log(
            "|ds| = seaborn.load_dataset(|ORIGIN|)",
            imports=["seaborn"],
            operation="import",
            origin=name,
            description="Import from Seaborn",
        )
        yield ds
