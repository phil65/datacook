from __future__ import annotations

import mdfreader

from processanalyzer.core import dataset
from processanalyzer.plugintypes import filereaderplugin


class MdfReader(filereaderplugin.FileReaderPlugin):
    menu_label = "MDF file"
    extensions = {"MDF files": [".mdf", ".mf4"]}
    plugin_id = "reader.mdf"

    # def is_valid_reader_for(self, path: pathlib.Path):
    # this would be for asammdf since it can read v2 dat mdf files
    #     if not super().is_valid_reader_for(path):
    #         return False
    #     if path.suffix.lower() != ".dat":
    #         return True
    #     num_bytes = min(1024, path.stat().st_size)
    #     with path.open(mode="rb") as file:
    #         raw = file.read(num_bytes)
    #     return raw.startswith(b"MDF")

    def read_file(self, path):
        dfs = mdfreader.Mdf(str(path)).convert_to_pandas()
        for i, df in enumerate(dfs):
            ds = dataset.DataSet(data=df, name=path.name)
            ds.log(
                f"|ds| = mdfreader.Mdf(|ORIGIN|).convert_to_pandas()[{i}]",
                imports=["mdfreader"],
                operation="import",
                origin=path,
                description="Import from MDF file",
            )
            yield ds
