"""Top-level package for DataCook QtCharts Plugin."""

import functools

from prettyqt import charts, core, gui, widgets
from processanalyzer.constants import iconnames
from processanalyzer.core import threads
from processanalyzer.gui import toolbars
from processanalyzer.util import colorgenerator

from . import chartutils, lineseries
from .seriesdialog import SeriesDialog
from .seriesmodel import SeriesModel
from .serieswidget import SeriesWidget

THEMES = charts.chart.THEMES


class ToolbarContainer(widgets.Widget):
    def __init__(self, widget, parent=None):
        """
        Container widget including a toolbar
        """

        super().__init__(parent=parent)
        toolbar = widget.get_toolbar()
        v_layout = widgets.BoxLayout("vertical", self, margin=0)
        v_layout += widget
        v_layout.setMenuBar(toolbar)


class ChartWidget(widgets.Splitter):

    """
    Custom chart widget (splitter) containing a GraphicsView and the series list
    """

    SeriesClass = lineseries.LineSeries

    def __init__(self, title="", parent=None):
        """
        Custom Widget composed of a plotting area and the series list
        """
        super().__init__("horizontal", parent=parent)
        self.color_gen = colorgenerator.ColorGenerator()
        self.set_title(title)
        self.plot_area = ChartArea(parent=self)
        container = ToolbarContainer(self.plot_area)
        self.add(container)
        self.list = SeriesWidget(self)
        self.plot_area.theme_changed.connect(self.list.update_model)
        self.add(self.list)
        self.setSizes([500, 200])

    @core.Slot()
    def finished(self):
        """
        should get called after lines are added / modified.
        sets up axes and markers
        """
        self.plot_area.chart().createDefaultAxes()
        model = SeriesModel(self.plot_area.chart)
        self.list.set_model(model)
        self.plot_area.chart().set_legend_alignment("right")
        self.plot_area.chart().hide_legend()
        self.plot_area.chart().update_boundaries()
        num_colors = self.color_gen.num_colors()
        for marker in self.plot_area.chart().legend().markers():
            marker.clicked.connect(self.plot_area.marker_clicked)
        for marker in self.plot_area.chart().legend().markers()[num_colors:]:
            marker.setVisible(False)
        self.setUpdatesEnabled(True)

    def add_series_async(self, ds):
        self.setUpdatesEnabled(False)
        worker = chartutils.ChartWorker(ds)
        worker.signals.add_lines.connect(self.add_series)
        worker.signals.finished.connect(self.finished)
        threads.pool.start(worker, set_busy=True, message="Preparing chart...")

    @core.Slot(object)
    def add_series(self, *series):
        for line in series:
            curve = self.SeriesClass()
            color = self.color_gen.color_by_name(line.name)
            pen = curve.pen()
            color = gui.Color(*color)
            with curve.block_signals():
                pen.setColor(color)
                pen.setWidthF(1.2)
                curve.setPen(pen)
                curve.setName(line.name)
                curve.process_name = line.process_name
                curve.append(line)
            curve.clicked.connect(self.list.select_series_by_sender)
            curve.doubleClicked.connect(self.open_prop_dialog)
            self.plot_area.chart().addSeries(curve)

    @core.Slot()
    def open_prop_dialog(self):
        """
        opens the properties dialog for the sender series
        """
        series = self.sender()
        dlg = SeriesDialog(parent=self, series=series)
        dlg.open_dialog()


class ChartArea(charts.ChartView):
    theme_changed = core.Signal()

    def __init__(self, title="", parent=None):
        """
        Custom TreeView for managing the imported data
        """

        # init some attribs
        super().__init__(parent=parent)
        self.set_title(title)

        # initialize chart
        # theme_name = config.settings.get("chart_theme", "Light")
        theme_name = "Light"
        self.set_theme(theme_name)
        self.chart().set_animation_options("series")

    def get_toolbar(self):
        tb = toolbars.ToolBar()
        labels_menu = widgets.Menu("Labels", icon=iconnames.STRING)
        labels_menu.add_action("Set chart title", self.set_chart_title)
        labels_menu.add_action("Set X axis label", self.set_x_label)
        labels_menu.add_action("Set Y axis label", self.set_y_label)
        tb.add_menu_button(label="Label", icon=iconnames.STRING, menu=labels_menu)

        theme_menu = widgets.Menu("Theme", icon=iconnames.THEME)
        for k, __ in THEMES.items():
            theme_menu.add_action(k, functools.partial(self.set_theme, k))
        tb.add_menu_button(label="Theme", icon=iconnames.THEME, menu=theme_menu)
        tb.add_action("Save as image", iconnames.SAVE, self.save_as_image)
        tb.add_action("Reset zoom", iconnames.RESET, self.chart().zoomReset)
        tb.add_action("Format axes", iconnames.FORMAT, self.chart().apply_nice_numbers)

        return tb

    @core.Slot(str)
    def set_theme(self, theme: str):
        """
        sets the chart theme
        """
        self.chart().set_theme(theme)
        self.theme_changed.emit()

    @core.Slot()
    def set_x_label(self):
        """
        let user set the x axis label
        """
        label = widgets.InputDialog.get_text(
            label="New X axis label", title="Edit Chart", icon=iconnames.PLOT
        )
        if label is not None:
            self.chart().axisX().setTitleText(label)

    @core.Slot()
    def set_y_label(self):
        """
        let user set the y axis label
        """
        label = widgets.InputDialog.get_text(
            label="New Y axis label", title="Edit Chart", icon=iconnames.PLOT
        )
        if label is not None:
            self.chart().axisY().setTitleText(label)

    @core.Slot()
    def set_chart_title(self):
        """
        let user set the title of the chart
        """
        label = widgets.InputDialog.get_text(
            label="Set chart title", title="Edit Chart", icon=iconnames.PLOT
        )
        if label is not None:
            self.chart().setTitle(label)

    @core.Slot()
    def marker_clicked(self):
        """
        Called when legend markes are clicked. show / hide clicked signal
        """
        clicked_marker = self.sender()
        clicked_marker_visible = clicked_marker.series().isVisible()
        clicked_name = clicked_marker.series().name()
        for marker in self.chart().legend().markers():
            if marker.series().name() != clicked_name:
                continue
            if clicked_marker_visible:
                marker.series().setVisible(False)
                alpha = 0.5
            else:
                marker.series().setVisible(True)
                alpha = 1.0
            marker.setVisible(True)
            brush = marker.labelBrush()
            color = brush.color()
            color.setAlphaF(alpha)
            brush.setColor(color)
            marker.setLabelBrush(brush)

            brush = marker.brush()
            color = brush.color()
            color.setAlphaF(alpha)
            brush.setColor(color)
            marker.setBrush(brush)
            pen = marker.pen()
            color = pen.color()
            color.setAlphaF(alpha)
            pen.setColor(color)
            marker.setPen(pen)
        # num_colors = self.color_gen.num_colors()
        # for marker in self.chart().legend().markers()[num_colors:]:
        #     marker.setVisible(False)


class ScatterChart(ChartWidget):
    SeriesClass = charts.ScatterSeries


if __name__ == "__main__":
    app = widgets.app()
    chart_widget = ChartWidget()
    from processanalyzer.core import dataset

    example = dataset.DataSet(dict(a=[1, 2, 3], b=[1, 2, 1]))
    chart_widget.add_series_async(example)
    chart_widget.resize(800, 800)
    chart_widget.show()
    app.main_loop()
