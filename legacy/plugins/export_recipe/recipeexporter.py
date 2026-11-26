from __future__ import annotations

from processanalyzer.constants import iconnames
from processanalyzer.plugintypes import exportplugin


class RecipeExporter(exportplugin.ExportPlugin):
    extension = ".recipe"
    menu_label = "Recipe file"
    icon = iconnames.RECIPE

    def export(self, ds):
        path = self.get_path()
        if not path:
            return None
        self.run(self.run_export, path, ds)

    def run_export(self, path, ds):
        with open(path, "w") as output:
            output.write(ds.history.to_yaml())
