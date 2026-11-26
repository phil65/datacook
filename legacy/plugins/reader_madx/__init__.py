from __future__ import annotations

import twisstool

from processanalyzer.core import dataset
from processanalyzer.plugintypes import filereaderplugin
from processanalyzer.constants import iconnames


class MadXReader(filereaderplugin.FileReaderPlugin):
    menu_label = "MadX file"
    extensions = {"MadX files": [".txt", ".tfs"]}
    plugin_id = "reader.madx"
    icon = iconnames.FILE

    def read_file(self, path):
        df = twisstool.twiss(str(path)).data
        ds = dataset.DataSet(data=df, name=path.name)
        ds.log(
            "|ds| = twisstool.twiss(|ORIGIN|).data",
            imports=["twisstool"],
            operation="import",
            origin=path,
            description="Import from Mad-X file",
        )
        yield ds
