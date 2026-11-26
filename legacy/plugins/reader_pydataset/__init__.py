from __future__ import annotations

import functools

import pydataset

from processanalyzer.constants import iconnames
from processanalyzer.core import dataset
from processanalyzer.gui.dialogs import tabledialog
from processanalyzer.plugintypes import readerplugin


class PyDataSetReader(readerplugin.ReaderPlugin):
    menu_label = "PyDataset"
    plugin_id = "reader.pydataset"
    icon = iconnames.DATABASE_SEARCH

    def read(self, path=None):
        table = dataset.DataSet(pydataset.data())
        dialog = tabledialog.TableDialog(df=table, title=self.menu_label)
        dialog.selected_indexes.connect(self.read_async)
        dialog.show_blocking()

    def read_async(self, indexes):
        selected = [x.data() for x in indexes if x.column() == 0]
        descriptions = [x.data() for x in indexes if x.column() == 1]
        gen = functools.partial(yield_datasets, selected, descriptions)
        self.yield_async(gen)


def yield_datasets(names, descriptions):
    for name, desc in zip(names, descriptions):
        ds = dataset.DataSet(data=pydataset.data(name), name=name, comment=desc)
        ds.log(
            "|ds| = pydataset.data(|ORIGIN|)",
            imports=["pydataset"],
            operation="import",
            origin=name,
            description="Import from PyDataset",
        )
        yield ds
