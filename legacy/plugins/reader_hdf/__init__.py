from __future__ import annotations

import logging

import pandas as pd

from processanalyzer.core import dataset, history
from processanalyzer.plugintypes import filereaderplugin

logger = logging.getLogger(__name__)


class HdfReader(filereaderplugin.FileReaderPlugin):
    extensions = {"Hdf5 files": [".hdf5"]}
    menu_label = "Hdf5 file"
    plugin_id = "reader.hdf"

    def read_file(self, path):
        with pd.HDFStore(path) as hdf:
            logger.info(hdf.keys())
            for key in hdf.keys():
                df = hdf.select(key)
                yaml_str = hdf.get_storer(key).attrs.metadata
                if yaml_str:
                    hist = history.History.build_from_string(yaml_str)
                    ds = dataset.DataSet(data=df, name=path.name, history=hist)
                else:
                    ds = dataset.DataSet(data=df, name=path.name)
                    ds.log(
                        "with pandas.HDFStore(|ORIGIN|) as hdf:",
                        f"    |ds| = hdf.select({key!r})",
                        imports=["pandas"],
                        operation="import",
                        origin=path,
                        description="Import from Hdf store",
                    )
                yield ds
