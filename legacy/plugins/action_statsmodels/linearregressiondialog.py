from __future__ import annotations

import logging

import statsmodels.api as sm
from statsmodels.graphics.regressionplots import abline_plot

from prettyqt import widgets
from processanalyzer.constants import iconnames
from processanalyzer.core import threads
from processanalyzer.core.application import _
from processanalyzer.gui import plotwidget
from processanalyzer.gui.dialogs import basecolumndialog

logger = logging.getLogger(__name__)


class LinearRegressionDialog(basecolumndialog.BaseColumnDialog):
    def __init__(self, parent=None, ds=None):
        super().__init__(
            parent=parent, ds=ds, title=_("Linear regression"), icon=iconnames.STATS
        )
        self.showMaximized()
        # columns = [col for col in ds.columns if ds[col].is_unique]
        self.filtered = None
        self.keyword_args = {}
        self.busy = False

        # filtered = ds[columns]
        self.list_cols_1 = self.add_feature_selector(
            "X", selection_mode="single", filter_dtypes=["object", "category"]
        )

        self.list_cols_2 = self.add_feature_selector(
            "Y", selection_mode="single", filter_dtypes=["object", "category"]
        )

        table_container_layout = widgets.BoxLayout("vertical")

        self.text_widget = widgets.PlainTextEdit()
        self.text_widget.set_read_only()
        self.text_widget.set_font("Consolas")
        table_container_layout += widgets.Label(_("Result"))
        table_container_layout += self.text_widget
        self.plot_widget = Plot()
        table_container_layout += self.plot_widget

        self.splitter += table_container_layout
        self.splitter.setStretchFactor(3, 3)

        self.add_buttonbox()

    def preview(self):
        colnames_1 = list(self.list_cols_1.selected_names())
        self.list_cols_2.model().set_disabled(colnames_1)
        colnames_2 = list(self.list_cols_2.selected_names())
        # self.list_columns_3.model().set_disabled(colnames_1 + colnames_2)
        # colnames_3 = self.list_columns_3.selected_names()
        if not colnames_1 or not colnames_2:
            return None
        self.keyword_args = dict(x=colnames_1[0], y=colnames_2[0])
        if not self.busy:
            worker = threads.Worker(self.load_async)
            worker.signals.result.connect(self.load_text_result)
            threads.pool.start(worker)

    def load_text_result(self, result):
        text = "" if result is None else str(result)
        self.text_widget.set_text(text)

    def load_async(self):
        """
        calc pivot table based on keyword_args and return it
        if keyword_args changed during calculations, call ourselves again
        to make sure preview is up to date
        self.busy stays True until we´re finished
        """
        self.busy = True
        keyword_args = self.keyword_args
        try:
            x = self.keyword_args["x"]
            y = self.keyword_args["y"]
            model = sm.OLS(self.ds[x], sm.add_constant(self.ds[y]), missing="drop")
            model = model.fit()
            # predictions = model.predict(ds[dlg.y])
            summary = model.summary()
            self.plot_widget.setup(self.ds, y, x, model)
            self.plot_widget.plot()
        except Exception as e:
            logger.exception(e)
            return None
        if keyword_args != self.keyword_args:
            return self.load_async()
        self.busy = False
        return summary


class Plot(plotwidget.PlotWidget):
    def setup(self, ds, x, y, model):
        self.ds = ds
        self.x = x
        self.y = y
        self.model = model
        if len(ds.index) > self.MAX_POINTS:
            self.ds = ds.sample(n=self.MAX_POINTS, random_state=1)

    def plot(self):
        self.axis.clear()
        self.ds.plot(x=self.x, y=self.y, kind="scatter", ax=self.axis, color="DarkGreen")
        abline_plot(model_results=self.model, ax=self.axis)
        self.fig.canvas.draw_idle()


if __name__ == "__main__":
    from processanalyzer.core import dataset

    app = widgets.app()
    ds = dataset.DataSet(dict(a=[1, 2, 3], b=[4, 5, 6]))
    dlg = LinearRegressionDialog(ds=ds)
    dlg.show_blocking()
