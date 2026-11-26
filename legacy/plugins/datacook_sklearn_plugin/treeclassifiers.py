from __future__ import annotations

import sklearn.tree
from prettyqt import widgets

import prettyqt.custom_widgets.dataset as fo

from processanalyzer.core import estimator
from processanalyzer.core.application import _

CRIT_OPTS = [("gini", _("Gini")), ("entropy", _("Entropy"))]

SPLIT_OPTS = [("best", _("Best split")), ("random", _("Best random split"))]

FEAT_OPTS = [(None, "n"), ("auto", _("Auto")), ("sqrt", "sqrt(n)"), ("log2", "log2(n)")]


class DecisionTreeClassifier(estimator.BaseTreeClassifier):
    obj = sklearn.tree.DecisionTreeClassifier
    alias = "Sklearn tree classifier"

    def get_param_class(self):
        class Dialog(fo.DataSet):
            criterion = fo.Enum(_("Criterion"), choices=CRIT_OPTS, radio=True)
            splitter = fo.Enum(_("Splitter"), choices=SPLIT_OPTS, radio=True)
            max_depth = fo.Int(_("Maximum tree depth for base learners"), value=3)
            max_features = fo.Enum(_("Max features"), choices=FEAT_OPTS, radio=True)

        return Dialog

    def dump_model(self):
        return {}

    def as_text(self):
        return sklearn.tree.export_text(self.instance)

    def plot(self, axis):
        sklearn.tree.plot_tree(self.instance, ax=axis)


if __name__ == "__main__":
    import pydataset
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure

    df = pydataset.data("kidtran")
    app = widgets.app()
    model = DecisionTreeClassifier()
    model.setup_kwargs()
    model.instance.fit(df.drop("race", axis=1), df["race"])
    fig = Figure()
    axis = fig.add_subplot(111)
    canvas = FigureCanvas(fig)
    canvas.show()
    # print(model.dump_model())
    print(model.as_text())
    model.plot(axis)
    app.main_loop()
