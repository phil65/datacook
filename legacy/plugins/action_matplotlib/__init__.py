from __future__ import annotations

import itertools
import logging

import pandas as pd
import seaborn as sns
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from prettyqt import core, widgets
from processanalyzer.constants import iconnames
from processanalyzer.core import signals, threads
from processanalyzer.plugintypes import contextmenuplugin

logger = logging.getLogger(__name__)


class MatPlotLibPlugin(contextmenuplugin.PluginAction):
    description = "Different kinds of plots for analysing a dataset."
    icon = iconnames.PLOT
    plugin_id = "context.matplotlib"
    short_desc = "Matplotshit"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.submenu_items = {
            "RegPlot": self.regplot,
            "BoxPlot": self.boxplot,
            "SwarmPlot": self.swarmplot,
            "ResidPlot": self.residplot,
            "RadViz": self.radviz,
        }

    def regplot(self):
        ds = next(self.selected_data())
        widget = RegPlot(ds)
        signals.signals.add_widget.emit(widget, "RegPlot")

    def boxplot(self):
        ds = next(self.selected_data())
        widget = BoxPlot(ds)
        signals.signals.add_widget.emit(widget, "BoxPlot")

    def swarmplot(self):
        ds = next(self.selected_data())
        widget = SwarmPlot(ds)
        signals.signals.add_widget.emit(widget, "SwarmPlot")

    def residplot(self):
        ds = next(self.selected_data())
        widget = ResidPlot(ds)
        signals.signals.add_widget.emit(widget, "ResidPlot")

    def radviz(self):
        ds = next(self.selected_data())
        widget = RadViz(ds)
        if not ds.select_dtypes(include=["category"]).columns.tolist():
            logger.info("Error: No category features in dataset.")
            return None
        signals.signals.add_widget.emit(widget, "RadViz")


class BaseWidget(widgets.Widget):
    MAX_POINTS = 1_000_000
    COLORS = [
        "tab:blue",
        "tab:orange",
        "tab:green",
        "tab:red",
        "tab:purple",
        "tab:brown",
        "tab:pink",
        "tab:gray",
        "tab:olive",
        "tab:cyan",
    ]

    def __init__(self, ds, **kwargs):
        super().__init__(**kwargs)
        self.ds = ds
        if len(ds.index) > self.MAX_POINTS:
            self.ds = ds.sample(n=self.MAX_POINTS, random_state=1)
            logger.info(
                "Dataset too large for plotting. "
                f"Taking a sample of {self.MAX_POINTS} points."
            )
        self.fig = Figure()
        self.axis = self.fig.add_subplot(111)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setStyleSheet("background-color:transparent;")
        self.canvas.setSizePolicy(
            widgets.SizePolicy.Expanding, widgets.SizePolicy.Expanding
        )
        self.canvas.updateGeometry()
        self.navi_toolbar = NavigationToolbar(self.canvas, self)
        self.layout = widgets.GridLayout(self)
        self.layout.addWidget(self.navi_toolbar)
        self.setLayout(self.layout)
        self.initialize(ds)
        self.layout.addWidget(self.canvas)
        self.async_update()

    def combobox(self, *dtypes):
        items = self.ds.select_dtypes(include=dtypes).columns.tolist()
        combo = widgets.ComboBox()
        combo.addItems(items)
        combo.currentIndexChanged.connect(self.async_update)
        return combo

    @core.Slot()
    def async_update(self):
        worker = threads.Worker(self.plot)
        threads.pool.start(worker)

    def plot(self):
        self.axis.clear()
        self.draw_plot()
        self.fig.canvas.draw_idle()

    def initialize(self, ds):
        raise NotImplementedError("No initialize defined")


class RegPlot(BaseWidget):
    NAME = "RegPlot"
    MAX_POINTS = 100000

    def initialize(self, ds):
        cats = self.ds.select_dtypes(include=["category", bool]).columns.tolist()
        self.dropdown_cats = self.combobox("category", bool)
        self.dropdown_x = self.combobox("number", "datetime")
        self.dropdown_y = self.combobox("number")
        if cats:
            self.layout.addWidget(widgets.Label("Category"))
            self.layout.addWidget(self.dropdown_cats)
        self.layout.addWidget(widgets.Label("X Axis"))
        self.layout.addWidget(self.dropdown_x)
        self.layout.addWidget(widgets.Label("Y Axis"))
        self.layout.addWidget(self.dropdown_y)

    def draw_plot(self):
        cat = self.dropdown_cats.currentText()
        xcol = self.dropdown_x.currentText()
        ycol = self.dropdown_y.currentText()
        if cat:
            datasets = [v.set_name(k) for k, v in self.ds.groupby(cat, observed=True)]
        else:
            datasets = [self.ds]
        self.axis.set_title(xcol)
        for c, ds in zip(itertools.cycle(self.COLORS), datasets):
            sns.regplot(x=xcol, y=ycol, data=ds, ax=self.axis, color=c, label=ds.title)
        self.axis.legend()


class RadViz(BaseWidget):
    NAME = "RadViz"
    MAX_POINTS = 20000

    def initialize(self, ds):
        to_exclude = ["category", "object"]
        self.num_cols = self.ds.select_dtypes(exclude=to_exclude).columns.tolist()
        self.dropdown_cats = self.combobox("category")
        self.layout.addWidget(self.dropdown_cats)

    def draw_plot(self):
        colname = self.dropdown_cats.currentText()
        pd.plotting.radviz(
            frame=self.ds[self.num_cols + [colname]],
            ax=self.axis,
            class_column=colname,
            colormap="Set1",
        )


class SwarmPlot(BaseWidget):
    NAME = "SwarmPlot"
    MAX_POINTS = 2000

    def initialize(self, ds):
        self.dropdown_x = self.combobox("category")
        self.dropdown_y = self.combobox("number")
        self.dropdown_z = self.combobox("category")
        self.layout.addWidget(self.dropdown_x)
        self.layout.addWidget(self.dropdown_y)
        self.layout.addWidget(self.dropdown_z)

    def draw_plot(self):
        sns.swarmplot(
            x=self.dropdown_x.currentText(),
            y=self.dropdown_y.currentText(),
            hue=self.dropdown_z.currentText(),
            data=self.ds,
            ax=self.axis,
        )


class SwarmBoxPlot(BaseWidget):
    NAME = "SwarmBoxPlot"
    MAX_POINTS = 2000

    def initialize(self, ds):
        self.dropdown_y = self.combobox("category")
        self.dropdown_x = self.combobox("number")
        self.dropdown_z = self.combobox("category")
        self.layout.addWidget(self.dropdown_x)
        self.layout.addWidget(self.dropdown_y)
        self.layout.addWidget(self.dropdown_z)

    def draw_plot(self):
        sns.boxplot(
            x=self.dropdown_x.currentText(),
            y=self.dropdown_y.currentText(),
            data=self.ds,
            ax=self.axis,
            whis="range",
            palette="vlag",
        )

        sns.swarmplot(
            x=self.dropdown_x.currentText(),
            y=self.dropdown_y.currentText(),
            hue=self.dropdown_z.currentText(),
            data=self.ds,
            ax=self.axis,
            size=2,
            # color=".3",
            linewidth=0,
        )
        self.axis.set_xscale("log")
        self.axis.xaxis.grid(True)
        self.axis.set(ylabel="")
        sns.despine(trim=True, left=True)


class ResidPlot(BaseWidget):
    NAME = "ResidPlot"
    MAX_POINTS = 5000

    def initialize(self, ds):
        self.dropdown_x = self.combobox("number")
        self.dropdown_y = self.combobox("number")
        self.layout.addWidget(self.dropdown_x)
        self.layout.addWidget(self.dropdown_y)

    def draw_plot(self):
        sns.residplot(
            x=self.dropdown_x.currentText(),
            y=self.dropdown_y.currentText(),
            lowess=True,
            data=self.ds,
            ax=self.axis,
        )


class BoxPlot(BaseWidget):
    NAME = "BoxPlot"
    MAX_POINTS = 20000

    def initialize(self, ds):
        self.ds = ds.select_dtypes(exclude=["category", "object"])

    def draw_plot(self):
        self.ds.boxplot(self.ds.columns.tolist(), ax=self.axis)
