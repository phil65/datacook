from __future__ import annotations

import pandas as pd

from processanalyzer.constants import iconnames
from processanalyzer.plugintypes import exportplugin


class HdfExporter(exportplugin.ExportPlugin):
    extension = ".hdf5"
    menu_label = "HDF5 file"
    icon = iconnames.FILE

    def export(self, ds):
        path = self.get_path()
        if not path:
            return None
        # keyword_args = dict(engine="blosc:snappy",
        #               format="table",
        #               key=str(ds.title))
        # ds.log(f"ds.to_hdf('{path}'|OPTKWARGS|)",
        #        operation="export",
        #        description="Export to .hdf5",
        #        kwargs=keyword_args)
        self.run(self.store, path, ds, "table")

    def store(self, filename, ds, key):
        with pd.HDFStore(filename) as store:
            store.put(key, ds.to_pandas_df(), format="table")
            store.get_storer(key).attrs.metadata = ds.history.to_yaml()
