from __future__ import annotations

import pantab

from processanalyzer.constants import iconnames
from processanalyzer.plugintypes import exportplugin


class TableauExporter(exportplugin.ExportPlugin):
    extension = ".hyper"
    menu_label = "Tableau .hyper file"
    icon = iconnames.PLOT

    def export(self, ds):
        path = self.get_path()
        if not path:
            return None
        self.run(self.store, path, ds)

    def store(self, filename, ds):
        pantab.frame_to_hyper(ds.to_pandas_df(), filename)
