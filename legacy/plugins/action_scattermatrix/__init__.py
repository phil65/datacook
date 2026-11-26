from __future__ import annotations

import logging
import time

import pandas as pd
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from prettyqt import widgets
from processanalyzer.constants import iconnames
from processanalyzer.core import categories, signals, threads
from processanalyzer.plugintypes import contextmenuplugin

logger = logging.getLogger(__name__)


class ScatterMatrixAction(contextmenuplugin.PluginAction):
    icon = iconnames.PLOT
    context_category = categories.PlotCategory
    description = "Show ScatterMatrix"
    short_desc = "ScatterMatrix"

    def is_visible(self):
        return self.model.content_type == "features" and len(self.indexes) > 1

    def process(self, **kwargs):
        ds = next(self.selected_data())
        widget = ScatterMatrix(ds, cols=self.columns)
        signals.signals.add_widget.emit(widget, "Scatter matrix")


class ScatterMatrix(widgets.Widget):
    MAX_POINTS = 100000

    def __init__(self, ds, **kwargs):
        self.cols = kwargs.pop("cols", None)
        super().__init__()
        self.ds = ds
        self.fig = Figure()
        self.axis = self.fig.add_subplot(111)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setStyleSheet("background-color:transparent;")
        self.canvas.setSizePolicy("expanding", "expanding")
        self.canvas.updateGeometry()
        layout = widgets.GridLayout()
        layout += NavigationToolbar(self.canvas)
        self.set_layout(layout)
        layout += self.canvas
        worker = threads.Worker(self.plot)
        threads.pool.start(worker)

    def plot(self):
        if len(self.ds.index) > self.MAX_POINTS:
            self.ds = self.ds.sample(n=self.MAX_POINTS, random_state=1)
            logger.info(
                "Dataset too large for plotting. "
                f"Taking a sample of {self.MAX_POINTS} points."
            )
        now = time.time()
        self.axis.clear()
        pd.plotting.scatter_matrix(self.ds[self.cols], alpha=0.2, ax=self.axis)
        self.fig.canvas.draw_idle()
        logger.info(f"Drawing took {time.time() - now} seconds.")
