from __future__ import annotations

import sklearn.cluster

import prettyqt.custom_widgets.dataset as fo

from processanalyzer.core import estimator
from processanalyzer.core.application import _

METHODS = [("bistochastic", _("Bistochastic")), ("scale", _("Scale")), ("log", _("Log"))]


class SpectralBiclusterer(estimator.BaseBiClusterer):
    alias = "Spectral biclustering"
    obj = sklearn.cluster.SpectralBiclustering

    def get_param_class(self):
        class Dialog(fo.DataSet):
            n_clusters = fo.Int(_("Clusters"), value=2, min_val=1)
            method = fo.Enum(_("Method"), choices=METHODS, radio=True)
            n_components = fo.Int(_("Number of singular vectors"), value=6, min_val=1)
            n_best = fo.Int(_("Number of best singular vectors"), min_val=1, value=3)
            mini_batch = fo.Bool(_("Use Mini-batch"))
            n_jobs = fo.Int(_("Jobs"), value=1, min_val=1)
            n_init = fo.Int(_("Number of runs"), min_val=1, value=10)

        return Dialog
