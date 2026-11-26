from __future__ import annotations

import sklearn.linear_model

import prettyqt.custom_widgets.dataset as fo

from processanalyzer.core import estimator
from processanalyzer.core.application import _

# from keras.layers import Dense
# from keras.models import Sequential


class LinearRegression(estimator.LinearModel):
    obj = sklearn.linear_model.LinearRegression
    alias = "Linear regression"

    def get_param_class(self):
        class Dialog(fo.DataSet):
            fit_intercept = fo.Bool(_("Fit intercept"), value=True)
            # normalize = fo.Bool(_("Normalize"))

        return Dialog

    def attributes(self):
        dct = {_("Coefficients"): self.instance.coef_}
        return dct
