from __future__ import annotations

import logging
import time

import seaborn as sns

from processanalyzer.constants import iconnames
from processanalyzer.core import categories, signals, threads
from processanalyzer.gui import plotwidget
from processanalyzer.plugintypes import contextmenuplugin

logger = logging.getLogger(__name__)


class DistPlotAction(contextmenuplugin.PluginAction):
    icon = iconnames.PLOT
    context_category = categories.PlotCategory
    description = "Show Distribution Plot"
    short_desc = "DistPlot"

    def is_visible(self):
        if len(self.indexes) != 1 or self.model.content_type != "features":
            return False
        return True

    def process(self, **kwargs):
        ds = self.model.ds
        col = next(self.selected_names())
        widget = DistPlot(ds, col=col)
        signals.signals.add_widget.emit(widget, f"Distribution for {col}")


class DistPlot(plotwidget.PlotWidget):
    MAX_POINTS = 1_000_000

    def __init__(self, ds, **kwargs):
        self.col = kwargs.pop("col", None)
        super().__init__(ds=ds, **kwargs)
        worker = threads.Worker(self.plot)
        threads.pool.start(worker)

    def plot(self):
        if len(self.ds.index) > self.MAX_POINTS:
            self.ds = self.ds.sample(n=self.MAX_POINTS, random_state=1)
            logger.info(
                f"Dataset too large for plotting. "
                f"Taking a sample of {self.MAX_POINTS} points."
            )
        now = time.time()
        self.axis.clear()
        sns.distplot(a=self.ds[self.col], rug=True, ax=self.axis)
        self.fig.canvas.draw_idle()
        logger.info(f"Drawing took {time.time() - now} seconds.")


class HeatmapAction(contextmenuplugin.PluginAction):
    icon = iconnames.PLOT
    context_category = categories.PlotCategory
    description = "Show heatmap"
    short_desc = "Heatmap"

    def is_visible(self):
        if len(self.indexes) != 1 or not self.model.content_type == "features":
            return False
        ds = next(self.selected_data())
        return len(ds.index) < 200

    def process(self, **kwargs):
        ds = next(self.selected_data())
        widget = Heatmap(ds)
        signals.signals.add_widget.emit(widget, self.short_desc)


class Heatmap(plotwidget.PlotWidget):
    def __init__(self, ds, **kwargs):
        super().__init__(ds=ds, **kwargs)
        worker = threads.Worker(self.plot)
        threads.pool.start(worker)

    def plot(self):
        self.axis = sns.heatmap(
            self.ds,
            ax=self.axis,
            annot=len(self.ds.index) < 30,
            xticklabels=True,
            yticklabels=True,
        )
