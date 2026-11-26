from __future__ import annotations

import nptdms

from processanalyzer.constants import iconnames
from processanalyzer.core import dataset
from processanalyzer.plugintypes import filereaderplugin


class TdmsReader(filereaderplugin.FileReaderPlugin):
    menu_label = "Tdms file"
    extensions = {"Tdms files": [".tdms"]}
    plugin_id = "reader.tdms"
    icon = iconnames.TIME

    def read_file(self, path):
        tdms_file = nptdms.TdmsFile(file=str(path))
        ds = dataset.DataSet(data=tdms_file.as_dataframe(), name=path.name)
        ds.log(
            "|ds| = nptdms.TdmsFile(file=|ORIGIN|).as_dataframe()",
            imports=["nptdms"],
            operation="import",
            origin=path,
            description="Import from Tdms file",
        )
        yield ds
