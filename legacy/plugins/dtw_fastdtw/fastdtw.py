from __future__ import annotations

import fastdtw
from scipy.spatial.distance import euclidean

import prettyqt.custom_widgets.dataset as fo
from processanalyzer.constants import iconnames
from processanalyzer.plugintypes import dtwplugin


class FastDTWPlugin(dtwplugin.DTWPlugin):
    plugin_id = "dtw.fastdtw"
    icon = iconnames.TOLERANCE_BANDS
    context_label = "DTW comparer (fastdtw package)"

    class Settings(fo.DataSet):
        window = fo.Float(
            "Window size", value=100.0, min_val=0.1, max_val=100.0, unit="%", slider=True
        )

    def compare(self, x1, x2):
        r, c = len(x1), len(x2)
        window = int(max(r, c) * self.settings.window)
        distance, path = fastdtw.fastdtw(x1, x2, radius=window, dist=euclidean)
        return distance
