from __future__ import annotations

import sklearn.ensemble

import prettyqt.custom_widgets.dataset as fo

from processanalyzer.core import estimator
from processanalyzer.core.application import _


class IsolationForest(estimator.BaseEnsemble):
    alias = "Isolation Forest"
    obj = sklearn.ensemble.IsolationForest

    def get_param_class(self):
        class Dialog(fo.DataSet):
            n_estimators = fo.Int(_("Number of estimators"), value=100)
            auto_cont = fo.Bool(_("Automatically determine contamination"), value=True)
            contamination = fo.Float(
                _("Contamination"),
                min_val=0.0,
                max_val=0.5,
                step=0.01,
                value=0.1,
                slider=True,
            )

            def to_dict(self):
                contamination = "auto" if self.auto_cont else self.contamination
                return dict(n_estimators=self.n_estimators, contamination=contamination)

        return Dialog
