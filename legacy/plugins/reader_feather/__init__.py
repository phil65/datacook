from __future__ import annotations

import multiprocessing as mp

import pandas as pd

from processanalyzer.constants import iconnames
from processanalyzer.core import dataset
from processanalyzer.plugintypes import filereaderplugin


class FeatherReader(filereaderplugin.FileReaderPlugin):
    extensions = {"Feather files": [".feather"]}
    menu_label = "Feather file"
    plugin_id = "reader.feather"
    icon = iconnames.FEATHER

    def read_file(self, path):
        cores = int(mp.cpu_count() * 0.75)
        df = pd.read_feather(path, cores=cores)
        ds = dataset.DataSet(data=df, name=path.name)
        ds.log(
            f"|ds| = pandas.read_feather(|ORIGIN|, cores={cores})",
            imports=["pandas"],
            operation="import",
            origin=path,
            description="Import from Feather file",
        )

        yield ds

        # for df in pf.iter_row_groups():
        #     yield pf.to_pandas()
