"""Top-level package for DataCook QtCharts Plugin."""

__author__ = """Philipp Temminghoff"""
__email__ = "phil65@kodi.tv"
__version__ = "0.1.0"
__copyright__ = f"Copyright 2019, {__author__}"
__maintainer__ = __author__
__status__ = "Production"
__title__ = "DataCook QtCharts plugin"


import logging

import pandas as pd

# import prettyqt.custom_widgets.dataset as fo
from prettyqt import charts

from processanalyzer.constants import iconnames
from processanalyzer.core import categories, dataset, signals
from processanalyzer.plugintypes import contextmenuplugin

from .chartwidget import ChartWidget

logger = logging.getLogger(__name__)

THEMES = charts.chart.THEMES


# class Settings(fo.DataSet):
#     default_theme = fo.Enum("Default theme", THEMES.keys())


class QtPlotAction(contextmenuplugin.PluginAction):
    icon = iconnames.PLOT
    context_category = categories.PlotCategory
    description = "Plot selected data as time series (using index for x-axis)."
    short_desc = "Show time series plot (new)"

    def is_visible(self):
        if len(self.indexes) == 0:
            return False
        data = next(self.selected_data())
        if isinstance(data, (dataset.DataSet, pd.Series)):
            return True
        return False

    def process(self, **kwargs):
        dfs = list(self.selected_data())
        if isinstance(dfs[0], pd.Series):
            dfs = dataset.DataSet(pd.concat(dfs, axis=1), name=f"{len(dfs)} feature(s)")
        ds = dfs
        if isinstance(ds, dataset.DataSet):
            ds = ds.select_dtypes(exclude=["datetime", "object", "category"])
            if ds.empty:
                logger.error("Nothing to plot.")
                return None
        title = f"{len(ds)} datasets" if isinstance(ds, list) else ds.title
        widget = ChartWidget()
        widget.set_title(title)
        # widget.set_icon(self.icon)
        widget.add_series_async(ds)
        signals.signals.add_widget.emit(widget, "Plot")
