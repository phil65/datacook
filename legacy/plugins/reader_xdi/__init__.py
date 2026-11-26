from __future__ import annotations

import xdi_pandas

from processanalyzer.core import dataset
from processanalyzer.plugintypes import filereaderplugin


class XdiReader(filereaderplugin.FileReaderPlugin):
    menu_label = "XDI file"
    extensions = {"XDI files": [".lcf", ".chir"]}
    plugin_id = "reader.xdi"

    def read_file(self, path):
        df = xdi_pandas.parse(str(path))
        ds = dataset.DataSet(data=df, name=path.name)
        ds.log(
            "|ds| = xdi_pandas.parse(|ORIGIN|)",
            imports=["xdi_pandas"],
            operation="import",
            origin=path,
            description="Import from XDI file",
        )
        yield ds
