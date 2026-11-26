from __future__ import annotations

import sklearn
import sklearn.pipeline
from prettyqt import itemmodels

from processanalyzer.constants import iconnames
from processanalyzer.core import dataset, history, historyitemmixin
from processanalyzer.core.application import _

BASE_URL = "https://scikit-learn.org/stable/modules/generated/"

TYPES = dict(
    classifier=sklearn.base.ClassifierMixin,
    regressor=sklearn.base.RegressorMixin,
    transformer=sklearn.base.TransformerMixin,
    cluster=sklearn.base.ClusterMixin,
)


class Estimator(historyitemmixin.HistoryItemMixin, itemmodels.NestedItem):
    obj: type = sklearn.base.BaseEstimator
    identifier: str
    alias: str | None = None
    icon: str
    item_name = "tf"

    def __init__(
        self,
        data: sklearn.base.BaseEstimator | None = None,
        name: str = "",
        history: history.History | None = None,
        comment: str = "",
        inherit_from: historyitemmixin.HistoryItemMixin | None = None,
        **kwargs,
    ):
        super().__init__(
            name=name or self.alias or "",
            history=history,
            comment=comment,
            inherit_from=inherit_from,
            **kwargs,
        )
        self.instance = self.obj() if data is None else data
        self.kwargs = self.instance.get_params()

    @classmethod
    def is_type(cls, typ: str) -> bool:
        return issubclass(cls.obj, TYPES[typ])

    def get_metadata(self) -> dict:
        return {}

    def get_tag(self, tag: str):
        """allows inspection of estimator capabilities

        allowed values: "allow_nan", "binary_only", "multilabel", "multioutput",
                        "multioutput_only", "no_validation", "non_deterministic",
                        "pairwise", "preserves_dtype", "poor_score", "requires_fit",
                        "requires_positive_X", "requires_y", "requires_positive_y",
                        "stateless", "X_types"

        Args:
            tag: tag to get

        Returns:
            value of the tag
        """
        tags = self.instance._get_tags()
        return tags.get(tag)

    @classmethod
    def help_url(cls) -> str:
        return f"{BASE_URL}{cls.module_name()}.html"

    @classmethod
    def import_module(cls) -> str:
        return ".".join(cls.obj.__module__.split(".")[:2])

    @classmethod
    def module_name(cls) -> str:
        return f"{cls.import_module()}.{cls.obj.__name__}"

    @classmethod
    def docs(cls) -> str:
        docs = cls.obj.__doc__
        return docs if docs is not None else ""

    def setup_kwargs(self) -> bool:
        Dialog = self.get_param_class()
        if Dialog is None:
            self.kwargs = {}
            return False
        dlg = Dialog(title=self.alias, icon=self.icon, comment=self.comment)
        if not dlg.edit():
            return False
        self.kwargs = dlg.to_dict()
        self.instance.set_params(**self.kwargs)
        self.log(
            "|tf|.set_params(|KWARGS|)", description="Set params", kwargs=self.kwargs
        )
        return True

    def get_param_class(self):
        return None

    def fit(self, ds, **kwargs):
        y = kwargs.pop("y")
        target_data = ds[y]
        train_data = ds.drop(y, axis=1)
        self.instance.fit(train_data, y=target_data)
        self.log(
            f"target_data = |CHILD_NAME_2|[{y!r}]",
            f"train_data = |CHILD_NAME_2|.drop({y!r}, axis=1)",
            "|tf| = |CHILD_NAME_1|.fit(train_data, y=target_data)",
            description="Fit",
            operation="merge",
            children=[self.history, ds.history],
            kwargs=kwargs,
        )
        return self

    def fit_transform(self, ds):
        ds = dataset.DataSet(
            self.instance.fit_transform(ds),
            columns=ds.columns,
            index=ds.index,
            inherit_from=ds,
        )
        ds.log(
            f"tf = {self.module_name()}(|KWARGS|)",
            "|ds| = pandas.DataFrame(tf.fit_transform(|ds|), "
            "columns=|ds|.columns, index=|ds|.index)",
            imports=["pandas", self.import_module()],
            description="Fit & transform",
            kwargs=self.kwargs,
        )
        return ds


class BaseTreeClassifier(Estimator):
    icon = iconnames.DECISION_TREE
    model_type = _("Tree classifier")
    identifier = "tree"

    def n_features(self) -> int:
        return self.instance.n_features_

    def get_booster(self):
        return self.instance.booster_

    def as_text(self) -> str:
        return ""

    def get_importance_df(self):
        ds = dataset.DataSet(
            data={_("Importances"): self.instance.feature_importances_},
            name=_("Importances"),
        )
        return ds


class BaseEnsemble(Estimator):
    icon = iconnames.CLUSTERER
    model_type = _("Ensemble algorithm")
    identifier = "ensemble"


class Pipeline(Estimator):
    icon = iconnames.PIPELINE
    model_type = _("Pipeline")
    identifier = "pipeline"
    obj = sklearn.pipeline.Pipeline
    alias = "Pipeline"

    def __init__(self, steps, *args, **kwargs):
        data = self.obj([(tf.alias, tf.instance) for tf in steps])
        super().__init__(data, *args, **kwargs)
        self.add_children(steps)


class BaseBiClusterer(Estimator):
    icon = iconnames.CLUSTERER
    model_type = _("Biclusterer")
    identifier = "biclusterer"


class BaseClusterer(Estimator):
    icon = iconnames.CLUSTERER
    model_type = _("Clusterer")
    identifier = "cluster"


class BaseDecompositor(Estimator):
    icon = iconnames.TRANSFORMER
    model_type = _("Decompositor")
    identifier = "decomposition"


class BaseImputer(Estimator):
    icon = iconnames.TRANSFORMER
    model_type = _("Imputer")
    identifier = "impute"


class LinearModel(Estimator):
    icon = iconnames.NEURALNETWORK
    model_type = _("Linear model")
    identifier = "linear_model"


class NeuralNetworkClassifier(Estimator):
    icon = iconnames.NEURALNETWORK
    model_type = _("Neural network")
    identifier = "neural_network"


class BasePreprocessor(Estimator):
    icon = iconnames.TRANSFORMER
    model_type = _("Preprocessors")
    identifier = "preprocessing"


class NeuralLayer:
    icon = iconnames.NEURALNETWORK
    model_type = _("Layer")
