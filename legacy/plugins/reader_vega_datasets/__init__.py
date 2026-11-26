from __future__ import annotations

import functools
import logging

import pandas as pd
import vega_datasets

from processanalyzer.constants import iconnames
from processanalyzer.core import dataset
from processanalyzer.gui.dialogs import tabledialog
from processanalyzer.plugintypes import readerplugin

logger = logging.getLogger(__name__)


class VegaDataSetReader(readerplugin.ReaderPlugin):
    menu_label = "Vega dataset"
    plugin_id = "reader.example.vega"
    icon = iconnames.DATABASE_SEARCH
    context_label = "Vega dataset reader"

    def read(self, path=None):
        dct = vega_datasets.core.Dataset._dataset_info
        ds = pd.DataFrame.from_dict(dct).T.reset_index()
        is_valid = ds["format"].isin(["json", "csv", "tsv"])
        ds = ds[is_valid]
        ds = ds[["index", "is_local", "description"]]
        dialog = tabledialog.TableDialog(df=ds, title="Vega dataset Reader")
        dialog.selected_indexes.connect(self.read_async)
        dialog.show_blocking()

    def read_async(self, indexes):
        selected = [x.data() for x in indexes if x.column() == 0]
        gen = functools.partial(yield_datasets, selected)
        self.yield_async(gen)


def yield_datasets(names):
    for name in names:
        try:
            df = vega_datasets.data(name)
        except ValueError as e:
            logger.error(e)
            continue
        try:
            desc = getattr(vega_datasets.data, name).description
        except AttributeError:
            desc = ""
        try:
            ds = dataset.DataSet(data=df, name=name, comment=desc)
            ds.log(
                "|ds| = vega_datasets.data(|ORIGIN|)",
                imports=["vega_datasets"],
                operation="import",
                origin=name,
                description="Import from Vega Datasets",
            )
        except (TypeError, ValueError) as e:
            logger.error(e)
            continue
        yield ds
