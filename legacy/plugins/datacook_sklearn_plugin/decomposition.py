from __future__ import annotations

import prettyqt.custom_widgets.dataset as fo
import sklearn.decomposition

from processanalyzer.core import estimator
from processanalyzer.core.application import _

SOLVERS = [
    ("auto", _("Auto")),
    ("full", _("Full")),
    ("arpack", _("Arpack")),
    ("randomized", _("Randomized")),
]


class PCA(estimator.BaseDecompositor):
    obj = sklearn.decomposition.PCA
    alias = "Principal component analysis"

    def get_param_class(self):
        class Dialog(fo.DataSet):
            n_components = fo.Int(
                _("PCA column amount"),
                value=1,
                min_val=1,
                optional=_("Set PCA feature amount manually"),
            )
            whiten = fo.Bool(_("Whiten"))
            svd_solver = fo.Enum(_("Solver"), choices=SOLVERS)

        return Dialog

    def attributes(self):
        # for components
        dct = {
            _("Explained variance"): self.instance.explained_variance_,
            _("Explained variance ratio"): self.instance.explained_variance_ratio_,
            _("Singular values"): self.instance.singular_values_,
        }
        return dct

        # logger.info("Variance ratio")
        # for colname, variance in zip(pca_ds.columns.tolist(),
        #                              pca.explained_variance_ratio_):
        #     logger.info(f"{colname}: {variance}")


class IncrementalPCA(estimator.BaseDecompositor):
    obj = sklearn.decomposition.IncrementalPCA
    alias = "Incremental PCA"

    def get_param_class(self):
        class Dialog(fo.DataSet):
            batch_size = fo.Int(
                _("Batch size"), value=1, min_val=1, optional=_("Set batch size manually")
            )
            n_components = fo.Int(_("PCA column amount"), value=1, min_val=1)

        return Dialog

    def attributes(self):
        # for components
        dct = {
            _("Explained variance"): self.instance.explained_variance_,
            _("Explained variance ratio"): self.instance.explained_variance_ratio_,
            _("Singular values"): self.instance.singular_values_,
        }
        return dct
