from __future__ import annotations

from pyaxis import pyaxis

from processanalyzer.constants import iconnames
from processanalyzer.core import dataset
from processanalyzer.plugintypes import filereaderplugin


class PxReader(filereaderplugin.FileReaderPlugin):
    menu_label = "PC-Axis file"
    extensions = {"Px files": [".px"]}
    plugin_id = "reader.px"
    icon = iconnames.BINARY

    def read_file(self, path):
        data = pyaxis.parse(str(path), encoding="ISO-8859-2")
        ds = dataset.DataSet(data=data["DATA"], name=path.name)
        ds.log(
            "data = pyaxis.parse(|ORIGIN|, encoding='ISO-8859-2')",
            "|ds| = data['DATA']",
            imports=["from pyaxis import pyaxis"],
            operation="import",
            origin=path,
            description="Import from Px file",
        )
        yield ds
