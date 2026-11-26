from __future__ import annotations

import prettyqt.custom_widgets.dataset as fo
import sklearn.preprocessing

from processanalyzer.core import estimator
from processanalyzer.core.application import _

NORM_METHODS = [("l1", "Lasso (L1)"), ("l2", "Ridge (L2)"), ("max", "Max")]

POWER_TRANSFORMS = [("yeo-johnson", _("Auto")), ("box-cox", _("Full"))]

DISTS = [("uniform", _("Uniform")), ("normal", _("Normal"))]

ENCODES = [("onehot-dense", "OneHot"), ("ordinal", "Ordinal")]
STRATEGIES = [("uniform", "Uniform"), ("quantile", "Quantile"), ("kmeans", "K-Means")]

OPTS = [("error", _("Error")), ("ignore", _("Ignore"))]


class PolynomialFeatures(estimator.BasePreprocessor):
    obj = sklearn.preprocessing.PolynomialFeatures
    alias = "Polynomial Features"

    def get_param_class(self):
        class Dialog(fo.DataSet):
            degree = fo.Int(_("Degree"), value=2)
            interaction_only = fo.Bool(_("Interaction features only"))
            include_bias = fo.Bool(_("Include bias column"), value=True)

        return Dialog


class QuantileTransformer(estimator.BasePreprocessor):
    obj = sklearn.preprocessing.QuantileTransformer
    alias = "Quantile Transformer"

    def get_param_class(self):
        class Dialog(fo.DataSet):
            n_quantiles = fo.Int(_("Number of quantiles"), value=1000)
            output_distribution = fo.Enum(
                _("Output distribution"), choices=DISTS, radio=True
            )
            subsample = fo.Int(_("Max number of samples"), value=10000)

        return Dialog


class PowerTransformer(estimator.BasePreprocessor):
    obj = sklearn.preprocessing.PowerTransformer
    alias = "Power Transformer"

    def get_param_class(self):
        class Dialog(fo.DataSet):
            method = fo.Enum(_("Method"), choices=POWER_TRANSFORMS, radio=True)
            standardize = fo.Bool(_("Standardize"))

        return Dialog

    def attributes(self):
        dct = {_("Lambdas"): self.instance.lambdas_}
        return dct


class Normalizer(estimator.BasePreprocessor):
    obj = sklearn.preprocessing.Normalizer
    alias = "Normalizer"

    def get_param_class(self):
        class Dialog(fo.DataSet):
            norm = fo.Enum(_("Normalization"), choices=NORM_METHODS, radio=True)

        return Dialog


class RobustScaler(estimator.BasePreprocessor):
    obj = sklearn.preprocessing.RobustScaler
    alias = "Robust Scaler"

    def get_param_class(self):
        class Dialog(fo.DataSet):
            with_centering = fo.Bool(_("Center data before scaling"), value=True)
            with_scaling = fo.Bool(_("Scale the data to interquartile range"), value=True)
            quantile_low = fo.Float(
                _("Lower quantile"), value=25, min_val=0, max_val=100, slider=True
            )
            quantile_high = fo.Float(
                _("Upper quantile"), value=75, min_val=0, max_val=100, slider=True
            )

            def to_dict(self):
                dct = super().to_dict()
                dct["quantile_range"] = (
                    dct.pop("quantile_low"),
                    dct.pop("quantile_high"),
                )
                return dct

        return Dialog

    def attributes(self):
        dct = {_("Center"): self.instance.center_, _("Scale"): self.instance.scale_}
        return dct


class StandardScaler(estimator.BasePreprocessor):
    obj = sklearn.preprocessing.StandardScaler
    alias = "Standard scaler"

    def get_param_class(self):
        class Dialog(fo.DataSet):
            with_mean = fo.Bool(_("Center data before scaling"), value=True)
            with_std = fo.Bool(_("Scale data to unit variance"), value=True)

        return Dialog

    def attributes(self):
        dct = {
            _("Relative scaling"): self.instance.scale_,
            _("Mean"): self.instance.mean_,
            _("Variance"): self.instance.var_,
        }
        return dct


class OneHotEncoder(estimator.BasePreprocessor):
    obj = sklearn.preprocessing.OneHotEncoder
    alias = "OneHot encoder"

    def get_param_class(self):
        class Dialog(fo.DataSet):
            sparse = fo.Bool(_("Sparse"), value=True)
            handle_unknown = fo.Enum(_("Handle unknown"), choices=OPTS)

        return Dialog


class KBinsDiscretizer(estimator.BasePreprocessor):
    obj = sklearn.preprocessing.KBinsDiscretizer
    alias = "KBins Discretizer"

    def get_param_class(self):
        class Dialog(fo.DataSet):
            equal_width = fo.Bool(_("Equal-width bins"))
            intervals = fo.FloatList(
                _("Intervals"), value=[20, 40], disabled_on="equal_width"
            )
            n_bins = fo.Int(
                _("Number of bins"),
                value=2,
                min_val=1,
                max_val=100,
                slider=True,
                enabled_on="equal_width",
            )
            encode = fo.Enum(_("Encoding method"), choices=ENCODES, radio=True)
            strategy = fo.Enum(_("Strategy"), choices=STRATEGIES, radio=True)

            def to_dict(self):
                dct = super().to_dict()
                intervals = dct.pop("intervals")
                if not dct.pop("equal_width"):
                    dct["n_bins"] = intervals
                return dct

        return Dialog

    def attributes(self):
        dct = {
            _("Number of bins"): self.instance.n_bins_,
            _("Bin edges"): self.instance.bin_edges_,
        }
        return dct


class MinMaxScaler(estimator.BasePreprocessor):
    obj = sklearn.preprocessing.MinMaxScaler
    alias = "MinMax scaler"

    def get_param_class(self):
        class Dialog(fo.DataSet):
            min = fo.Int(_("Range min"))
            max = fo.Int(_("Range max"), value=1)

            def to_dict(self):
                return dict(feature_range=(self.min, self.max))

        return Dialog

    def attributes(self):
        dct = {
            _("Min"): self.instance.min_,
            _("Scale"): self.instance.scale_,
            _("Data min"): self.instance.data_min_,
            _("Data max"): self.instance.data_max_,
            _("Data range"): self.instance.data_range_,
        }
        return dct


class MaxAbsScaler(estimator.BasePreprocessor):
    obj = sklearn.preprocessing.MaxAbsScaler
    alias = "MaxAbs scaler"

    def get_param_class(self):
        return None

    def attributes(self):
        dct = {
            _("Relative scale"): self.instance.scale_,
            _("Maximum"): self.instance.max_abs_,
        }
        return dct
