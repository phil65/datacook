from __future__ import annotations

from processanalyzer.constants import iconnames
from processanalyzer.core import categories, dataset
from processanalyzer.plugintypes import contextmenuplugin

from .linearregressiondialog import LinearRegressionDialog


class LinearRegressionAction(contextmenuplugin.PluginAction):
    icon = iconnames.STATS
    context_category = categories.StatsCategory
    description = "Apply Linear regression"
    short_desc = "Linear regression"

    def is_visible(self):
        if len(self.indexes) != 1:
            return False
        data = next(self.selected_data())
        if isinstance(data, dataset.DataSet):
            return True
        return False

    def process(self, **kwargs):
        ds = next(self.selected_data())
        dialog = LinearRegressionDialog(ds=ds)
        dialog.show_blocking()
