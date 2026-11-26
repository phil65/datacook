from __future__ import annotations

import lightgbm
from prettyqt import widgets

import prettyqt.custom_widgets.dataset as fo

from processanalyzer.core import dataset, estimator
from processanalyzer.core.application import _

TYPES = [
    ("gbdt", _("Traditional Gradient Boosting Decision Tree")),
    ("dart", _("Dropouts meet Multiple Additive Regression Tree")),
    ("goss", _("Gradient-based one-side sampling")),
    ("rf", _("Random forest")),
]


class LightGBMClassifier(estimator.BaseTreeClassifier):
    obj = lightgbm.sklearn.LGBMClassifier
    alias = "LightGBM tree classifier"

    @classmethod
    def help_url(cls):
        return (
            "https://lightgbm.readthedocs.io/en/latest/Python-API.html"
            "#scikit-learn-api"
        )

    def get_param_class(self):
        class Dialog(fo.DataSet):
            boosting_type = fo.Enum(_("Boosting type"), choices=TYPES, radio=True)
            num_leaves = fo.Int(_("Maximum tree leaves for base learners"), value=31)
            max_depth = fo.Int(_("Maximum tree depth for base learners"), value=3)
            learning_rate = fo.Float(_("Learning rate"), value=0.1)
            n_estimators = fo.Int(_("Number of boosted trees to fit"), value=100)
            subsample_for_bin = fo.Int(
                _("Number of samples for constructing bins"), value=200000
            )
            min_split_gain = fo.Float(
                _("Minimum loss reduction required to make a further partition"),
                value=0.0,
            )
            min_child_weight = fo.Float(
                _("Minimum sum of instance weight needed in a child (leaf)"), value=0.001
            )
            min_child_samples = fo.Int(
                _("Minimum number of data needed in a child"), value=20
            )

        return Dialog

    def get_importance_df(self):
        booster = self.get_booster()
        ds = dataset.DataSet(
            data={
                _("Feature"): booster.feature_name(),
                _("Importances"): booster.feature_importance(),
            },
            name=_("Importances"),
        )
        ds.reset_index(drop=True, inplace=True)
        return ds

    def dump_model(self):
        booster = self.get_booster()
        return booster.dump_model()["tree_info"][0]

    def plot(self, axis):
        lightgbm.plot_tree(
            self.instance.booster_, ax=axis, figsize=(20, 8), show_info=["split_gain"]
        )


if __name__ == "__main__":
    import pydataset
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure

    df = pydataset.data("kidtran")
    app = widgets.app()
    model = LightGBMClassifier()
    model.setup_kwargs()
    model.instance.fit(df.drop("race", axis=1), df["race"])
    fig = Figure()
    axis = fig.add_subplot(111)
    canvas = FigureCanvas(fig)
    canvas.show()
    print(model.dump_model())
    model.plot(axis)
    app.main_loop()
