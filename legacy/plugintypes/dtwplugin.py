from __future__ import annotations

from processanalyzer.plugintypes import baseplugin


class DTWPlugin(baseplugin.BasePlugin):
    plugin_category = "DTW"

    def __init__(self, *args, **kwargs):
        if self.Settings is not None:
            self.settings = self.Settings(title=self.context_label, icon=self.icon)

    def compare(self, x1, x2):
        """
        compare two series, return distance
        """
        pass
