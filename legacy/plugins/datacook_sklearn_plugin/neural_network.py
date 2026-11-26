from __future__ import annotations

import prettyqt.custom_widgets.dataset as fo

# import nolearn.lasagne
import sklearn.neural_network

from processanalyzer.core import estimator
from processanalyzer.core.application import _

ACTIVATION_METHODS = [
    ("identity", _("No-op activation")),
    ("logistic", _("Logistic sigmoid function")),
    ("tanh", _("Hyperbolic tan function")),
    ("relu", _("Rectified linear unit function")),
]

SOLVERS = [
    ("lbfgs", _("Quasi-Newton optimizer")),
    ("sgd", _("Stochastic gradient descent")),
    ("adam", _("Adam optimizer")),
]

# learning_rates = [("constant", "quasi-Newton optimizer"),
#            ("invscaling", "stochastic gradient descent"),
#            ("adaptive", "Adam optimizer")]

# class NolearnNeuralNet(estimator.NeuralNetworkClassifier):

#     obj = nolearn.lasagne.NeuralNet
#     alias = "Nolearn Neural net"

#     def get_param_class(self):

#         types = []

#         class Dialog(fo.DataSet):
#             booster = fo.Enum(_("Boosting type"), choices=types, radio=True)
#             max_depth = fo.Int(_("Maximum tree depth for base learners"), value=3)
#             learning_rate = fo.Float(_("Learning rate"), value=0.1)
#             n_estimators = fo.Int(_("Number of boosted trees to fit"), value=100)
#             min_child_weight = fo.Int(
#                 _("Minimum sum of instance weight needed in a child (leaf)"), value=1)

#         return Dialog


class MLPClassifier(estimator.NeuralNetworkClassifier):
    obj = sklearn.neural_network.MLPClassifier
    alias = "MLP Neural network"

    def get_param_class(self):
        class Dialog(fo.DataSet):
            hidden_layer_sizes = fo.String(_("Layers"), notempty=True)
            activation = fo.Enum(_("Activation function"), choices=ACTIVATION_METHODS)
            solver = fo.Enum(_("Solver"), choices=SOLVERS)
            alpha = fo.Float(_("Learning rate"), value=0.1)
            max_iter = fo.Int(_("Max iterations"), value=200)

            def to_dict(self):
                dct = super().to_dict()
                dct["hidden_layer_sizes"] = (self.hidden_layer_sizes,)
                return dct

        return Dialog
