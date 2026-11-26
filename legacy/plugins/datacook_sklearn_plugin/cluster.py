from __future__ import annotations

import sklearn.cluster

import prettyqt.custom_widgets.dataset as fo
from processanalyzer.core import estimator
from processanalyzer.core.application import _

LINKAGES = [
    ("ward", _("Ward")),
    ("complete", _("Complete")),
    ("average", _("Average")),
    ("single", _("Single")),
]

TREE_OPTS = [("auto", _("Auto")), (False, _("False")), (True, _("True"))]


class KMeansCluster(estimator.BaseClusterer):
    alias = "K-Means clustering"
    obj = sklearn.cluster.KMeans

    def get_param_class(self):
        class Dialog(fo.DataSet):
            n_clusters = fo.Int(_("Clusters"), value=2, min_val=1)
            n_init = fo.Int(_("Number of runs"), min_val=1, value=10)
            max_iter = fo.Int(_("Max iterations"), min_val=1, value=300)
            random_state = fo.Int(_("Random state"), value=1)
            tol = fo.Float(_("Tolerance"), value=0.0001, min_val=0.0, max_val=1.0)

        return Dialog


class MiniBatchKMeans(estimator.BaseClusterer):
    alias = "Mini-Batch K-Means clustering"
    obj = sklearn.cluster.MiniBatchKMeans

    def get_param_class(self):
        class Dialog(fo.DataSet):
            n_clusters = fo.Int(_("Clusters"), value=2, min_val=2)
            max_iter = fo.Int(_("Max iterations"), min_val=1, value=100)
            batch_size = fo.Int(_("Batch size"), min_val=1, value=100)
            random_state = fo.Int(_("Random state"), value=1)
            tol = fo.Float(_("Tolerance"), value=0.0, min_val=0.0)
            max_no_improvement = fo.Int(_("Max no improvement"), min_val=1, value=10)
            reassignment_ratio = fo.Float(
                _("Reassignment ratio"),
                value=0.01,
                min_val=0.0,
                max_val=1.0,
                step=0.01,
                slider=True,
            )

        return Dialog


class SpectralClustering(estimator.BaseClusterer):
    alias = "Spectral Clustering"
    obj = sklearn.cluster.SpectralClustering

    def get_param_class(self):
        class Dialog(fo.DataSet):
            n_clusters = fo.Int(_("Clusters"), value=2, min_val=2)
            n_jobs = fo.Int(_("Jobs"), value=1, min_val=1)
            random_state = fo.Int(_("Random state"), value=1)

        return Dialog


class AgglomerativeClustering(estimator.BaseClusterer):
    alias = "Agglomerative Clustering"
    obj = sklearn.cluster.AgglomerativeClustering

    def get_param_class(self):
        class Dialog(fo.DataSet):
            n_clusters = fo.Int(_("Number of clusters"), value=2, min_val=1)
            compute_full_tree = fo.Enum(
                _("Compute full tree"), choices=TREE_OPTS, radio=True
            )
            linkage = fo.Enum(_("Linkage"), choices=LINKAGES, radio=True)

        return Dialog
