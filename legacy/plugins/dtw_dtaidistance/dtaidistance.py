from __future__ import annotations

import pandas as pd
from dtaidistance import dtw
from dtaidistance import dtw_visualisation as dtwvis

import prettyqt.custom_widgets.dataset as fo
from processanalyzer.constants import iconnames
from processanalyzer.core import signals, threads
from processanalyzer.gui import plotwidget
from processanalyzer.plugintypes import contextmenuplugin, dtwplugin


class DtaidistanceDTW(dtwplugin.DTWPlugin):
    plugin_id = "dtw.dtaidistance"
    icon = iconnames.TOLERANCE_BANDS
    context_label = "DTW comparer (dtaidistance package)"

    class Settings(fo.DataSet):
        psi = fo.Float("Psi factor", value=0.0, min_val=0.0)
        penalty = fo.Float("Penalty", value=0.0, min_val=0.0)
        window = fo.Float(
            "Window size", value=100.0, min_val=0.1, max_val=100.0, unit="%", slider=True
        )

    def compare(self, x1, x2):
        if isinstance(x1, pd.Series):
            x1 = x1.to_numpy()
        if isinstance(x2, pd.Series):
            x2 = x2.to_numpy()
        r, c = len(x1), len(x2)
        window = int(max(r, c) * self.settings.window)
        return dtw.distance_fast(
            x1.astype("float64"),
            x2.astype("float64"),
            window=window,
            penalty=self.settings.penalty,
            psi=self.settings.psi,
        )


class WarpingPathsAction(contextmenuplugin.PluginAction):
    icon = iconnames.PLOT
    description = "Plot DTW distances"
    short_desc = "Plot DTW distances"

    def is_visible(self):
        if len(self.indexes) != 1 or self.model.content_type != "groups":
            return False
        return True

    def process(self, **kwargs):
        ds = self.model.ds
        col = next(self.selected_names())
        widget = WarpingPathWidget(ds, col=col)
        signals.signals.add_widget.emit(widget, f"Warping paths for {col}")


class WarpingPathWidget(plotwidget.PlotWidget):
    NAME = "WarpingPaths"

    def __init__(self, ds, **kwargs):
        self.col = kwargs.pop("col", None)
        super().__init__(ds=ds, **kwargs)
        worker = threads.Worker(self.plot)
        threads.pool.start(worker)

    def plot(self):
        col = self.dropdown_nums.currentText()
        matrix = [group[col].to_numpy() for (name, group) in self.ds.groupby(self.col)]
        matrix = dtw.distance_matrix_fast(matrix)
        self.axis = dtwvis.plot_matrix(matrix, ax=self.axis)
