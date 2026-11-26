from __future__ import annotations

import numpy as np
import prettyqt.custom_widgets.dataset as fo
import sklearn.impute

from processanalyzer.core import estimator
from processanalyzer.core.application import _

CHOICES = [
    ("mean", _("Mean")),
    ("median", _("Median")),
    ("most_frequent", _("Most frequent")),
]


class SimpleImputer(estimator.BaseImputer):
    obj = sklearn.impute.SimpleImputer
    alias = "Imputer"

    def get_param_class(self):
        class Dialog(fo.DataSet):
            strategy = fo.Enum(_("Strategy"), choices=CHOICES, radio=True)
            fill_value = fo.String(_("Fill value"), value="0", notempty=True)
            missing_values = fo.Fixed(_("Missing values"), value=np.nan)

        return Dialog


# class MissingIndicator(BaseTransformer):

#     obj = sklearn.impute.MissingIndicator
#     alias = "MissingIndicator"

#     def get_param_class(self):

#         class Dialog(fo.DataSet):
#             strategy = fo.Enum(_("Strategy"),
#                                      choices=choices,
#                                      radio=True)
#             fill_value = fo.String(_("Fill value"),
#                                        value="0",
#                                        notempty=True)

#             def to_dict(self):
#                 return dict(missing_values=np.nan,
#                             strategy=self.strategy,
#                             fill_value=self.fill_value)

#         return Dialog
