from __future__ import annotations

import logging


from processanalyzer.constants import iconnames
from processanalyzer.core.application import _
from processanalyzer.core import dataset
from processanalyzer.methods import methods

logger = logging.getLogger(__name__)

SIDE_OPTS = [(None, _("Default")), ("left", _("Left")), ("right", _("Right"))]


class SetParamsMethod(methods.BaseMethod):
    icon = iconnames.ESTIMATOR
    description = _("Fit")
    short_desc = _("Fit")
    obj = None

    def apply_method(self, estimator):
        Dialog = estimator.get_param_class()
        preset = estimator.instance.get_params()
        if Dialog is None:
            return None
        dlg = Dialog(
            title=estimator.alias, icon=estimator.icon, comment=estimator.comment
        )
        if not dlg.edit(preset):
            return None
        keyword_args = dlg.to_dict()
        estimator.instance.set_params(**keyword_args)
        estimator.log(
            "|tf|.set_params(|KWARGS|)", description="Set params", kwargs=keyword_args
        )
        return True


class FitMethod(methods.BaseMethod):
    icon = iconnames.ESTIMATOR
    description = _("Fit")
    short_desc = _("Fit")
    obj = None

    def apply_method(self, estimator, ds):
        keyword_args = self.params.to_dict()
        y = keyword_args.pop("y")
        target_data = ds[y]
        train_data = ds.drop(y, axis=1)
        estimator.instance.fit(train_data, y=target_data)
        estimator.log(
            f"target_data = |CHILD_NAME_2|[{y!r}]",
            f"train_data = |CHILD_NAME_2|.drop({y!r}, axis=1)",
            "|tf| = |CHILD_NAME_1|.fit(train_data, y=target_data)",
            description="Fit",
            operation="merge",
            children=[estimator.history, ds.history],
            kwargs=keyword_args,
        )
        return estimator


class FitTransformMethod(methods.BaseMethod):
    icon = iconnames.ESTIMATOR
    description = _("Fit and transform")
    short_desc = _("Fit and transform")
    obj = None

    def apply_method(self, estimator, ds):
        ds = dataset.DataSet(
            estimator.instance.fit_transform(ds),
            columns=ds.columns,
            index=ds.index,
            inherit_from=ds,
        )
        ds.log(
            f"tf = {estimator.module_name()}(|KWARGS|)",
            "|ds| = pandas.DataFrame(tf.fit_transform(|ds|), "
            "columns=|ds|.columns, index=|ds|.index)",
            imports=["pandas", estimator.import_module()],
            description="Fit & transform",
            kwargs=estimator.kwargs,
        )
        return ds


class TransformMethod(methods.BaseMethod):
    icon = iconnames.ESTIMATOR
    description = _("Fit and transform")
    short_desc = _("Fit and transform")
    obj = None

    def apply_method(self, estimator, ds):
        ds = dataset.DataSet(
            estimator.instance.transform(ds),
            columns=ds.columns,
            index=ds.index,
            inherit_from=ds,
        )
        ds.log(
            f"tf = {estimator.module_name()}(|KWARGS|)",
            "|ds| = pandas.DataFrame(tf.transform(|ds|), "
            "columns=|ds|.columns, index=|ds|.index)",
            imports=["pandas", estimator.import_module()],
            description="Fit & transform",
            kwargs=estimator.kwargs,
        )
        return ds


class PredictMethod(methods.BaseMethod):
    icon = iconnames.ESTIMATOR
    description = _("Predict")
    short_desc = _("Predict")
    obj = None

    def apply_method(self, estimator, ds, feat_name):
        ds[feat_name] = estimator.instance.predict(ds)
        ds.log(
            f"|ds|[{feat_name}] = |CHILD_NAME_1|.predict(|CHILD_NAME_2|)",
            imports=[estimator.import_module()],
            children=[estimator.history, ds.history],
            description="Fit & predict",
            kwargs=estimator.kwargs,
        )
        return ds


class FitPredictMethod(methods.BaseMethod):
    icon = iconnames.ESTIMATOR
    description = _("Fit & Predict")
    short_desc = _("Fit & Predict")
    obj = None

    def apply_method(self, estimator, ds, colnames, feat_name="cluster"):
        ds[feat_name] = estimator.instance.fit_predict(ds[colnames])
        ds.log(
            f"tf = {estimator.module_name()}(|KWARGS|)",
            f"|ds|[{feat_name}] = tf.fit_predict(|ds|[{colnames}])",
            imports=[estimator.import_module()],
            description="Fit & predict",
            kwargs=estimator.kwargs,
        )
        return ds


if __name__ == "__main__":
    from prettyqt import widgets

    app = widgets.app()
