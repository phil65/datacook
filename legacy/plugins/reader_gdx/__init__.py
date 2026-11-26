from __future__ import annotations

import gdxpds

from processanalyzer.core import dataset
from processanalyzer.plugintypes import filereaderplugin
from processanalyzer.constants import iconnames


class GdxReader(filereaderplugin.FileReaderPlugin):
    menu_label = "GAMS data file"
    extensions = {"GAMS data files": [".gdx"]}
    plugin_id = "reader.gdx"
    icon = iconnames.BINARY

    def read_file(self, path):
        dfs = gdxpds.to_dataframes(str(path))
        for i, df in enumerate(dfs):
            ds = dataset.DataSet(data=df, name=path.name)
            ds.log(
                f"|ds| = gdxpds.to_dataframes(|ORIGIN|)[{i}]",
                imports=["gdxpds"],
                operation="import",
                origin=path,
                description="Import from GDX file",
            )
            yield ds
