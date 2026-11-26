from __future__ import annotations

import io
import json

import prettyqt.custom_widgets.dataset as fo
import xgboost
from prettyqt import widgets

from processanalyzer.core import dataset, estimator
from processanalyzer.core.application import _

BOOST_TYPES = [("gbtree", _("Tree")), ("gblinear", _("Linear")), ("dart", _("Dart"))]


class XGBoostClassifier(estimator.BaseTreeClassifier):
    obj = xgboost.XGBClassifier
    alias = "XGBoost tree classifier"

    def get_param_class(self):
        class Dialog(fo.DataSet):
            # _boostertype = dt.GetAttrProp("booster")
            # .set_active(dt.FuncProp(_boostertype), lambda x: x == "gbtree")
            booster = fo.Enum(_("Boosting type"), choices=BOOST_TYPES, radio=True)
            max_depth = fo.Int(_("Maximum tree depth for base learners"), value=3)
            learning_rate = fo.Float(_("Learning rate"), value=0.1)
            n_estimators = fo.Int(_("Number of boosted trees to fit"), value=100)
            min_child_weight = fo.Int(
                _("Minimum sum of instance weight needed in a child (leaf)"), value=1
            )

        return Dialog

    def n_features(self):
        return self.instance._features_count

    @classmethod
    def help_url(cls):
        return (
            "https://xgboost.readthedocs.io/en/latest/python/python_api.html"
            "#module-xgboost.sklearn"
        )

    def plot(self, axis):
        xgboost.plot_tree(booster=self.get_booster(), rankdir="LR", ax=axis)

    def get_importance_df(self):
        booster = self.get_booster()
        ds = dataset.DataSet(
            data=booster.get_fscore(),
            index=[_("Feature"), _("Importance")],
            name=_("Importances"),
        ).T
        ds.iloc[:, 0] = ds.index
        ds.sort_values(_("Importance"), inplace=True, ascending=False)
        ds.reset_index(drop=True, inplace=True)
        return ds

    def get_booster(self):
        return self.instance.get_booster()

    def dump_model(self):
        booster = self.get_booster()
        buf = io.StringIO()
        booster.dump_model(fout=buf, dump_format="json", with_stats=True)

        # root_item = cls(parent=parent)
        # root_item.key = "root"
        # if isinstance(value, dict):
        #     value.pop("nodeid", None)
        #     value.pop("depth", None)
        #     value.pop("yes", None)
        #     value.pop("no", None)
        #     value.pop("missing", None)
        #     items = sorted(value.items()) if sort else value.items()
        #     for key, value in items:
        #         child = cls.load(value, root_item)
        #         child.key = key
        #         child.type = type(value)
        #         root_item.append_child(child)

        # elif isinstance(value, list):
        #     for index, value in enumerate(value):
        #         child = cls.load(value, root_item)
        #         child.key = _("yes") if index == 0 else _("no")
        #         child.type = type(value)
        #         root_item.append_child(child)

        # else:
        #     root_item.value = value
        #     root_item.type = type(value)

        return json.loads(buf.getvalue())[0]

    def as_text(self):
        booster = self.get_booster()
        buf = io.StringIO()
        booster.dump_model(fout=buf, dump_format="text", with_stats=True)
        return buf.getvalue()


if __name__ == "__main__":
    import pydataset
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure

    df = pydataset.data("kidtran")
    app = widgets.app()
    model = XGBoostClassifier()
    model.setup_kwargs()
    model.instance.fit(df.drop("race", axis=1), df["race"])
    fig = Figure()
    ax = fig.add_subplot(111)
    canvas = FigureCanvas(fig)
    canvas.show()
    print(model.as_text())
    model.plot(ax)
    app.main_loop()
