from __future__ import annotations

import pyreadr

from processanalyzer.constants import iconnames
from processanalyzer.core import dataset
from processanalyzer.plugintypes import filereaderplugin


class RReader(filereaderplugin.FileReaderPlugin):
    menu_label = "R files"
    extensions = {"R data files": [".rds", ".rdata"]}
    plugin_id = "reader.r"
    icon = iconnames.R

    def read_file(self, path):
        ds = dataset.DataSet(data=pyreadr.read_r(path), name=path.name)
        ds.log(
            "|ds| = pyreadr.read_r(|ORIGIN|)",
            imports=["pyreadr"],
            operation="import",
            origin=path,
            description="Import from R data file",
        )
        yield ds
