from __future__ import annotations

import fastparquet

from processanalyzer.core import dataset
from processanalyzer.plugintypes import filereaderplugin


class ParquetReader(filereaderplugin.FileReaderPlugin):
    extensions = {"Parquet files": [".parquet"]}
    menu_label = "Parquet file"
    plugin_id = "reader.parquet"

    def read_file(self, path):
        pf = fastparquet.ParquetFile(str(path))
        ds = dataset.DataSet(data=pf.to_pandas(), name=path.name)
        ds.log(
            "|ds| = fastparquet.ParquetFile(|ORIGIN|).to_pandas()",
            imports=["fastparquet"],
            operation="import",
            origin=path,
            description="Import from FastParquet",
        )
        yield ds

        # for df in pf.iter_row_groups():
        #     yield pf.to_pandas()
