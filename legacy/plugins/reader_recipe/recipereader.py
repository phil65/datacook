from __future__ import annotations

from processanalyzer.constants import iconnames
from processanalyzer.core import history
from processanalyzer.plugintypes import filereaderplugin


class RecipeReader(filereaderplugin.FileReaderPlugin):
    menu_label = "Recipe"
    extensions = {"Recipes": [".recipe"]}
    icon = iconnames.RECIPE
    plugin_id = "plugin.recipe"

    def read_file(self, path):
        hist = history.History.build_from_string(path.read_text())
        ds = hist.evaluate()
        ds.set_name(path.name)
        yield ds
