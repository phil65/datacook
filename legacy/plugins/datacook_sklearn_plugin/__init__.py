"""Top-level package for DataCook SciKit-Learn plugin."""

__author__ = """Philipp Temminghoff"""
__email__ = "phil65@kodi.tv"
__version__ = "0.1.0"
__copyright__ = f"Copyright 2019, {__author__}"
__maintainer__ = __author__
__status__ = "Production"
__title__ = "DataCook Scikit-learn plugin"


from .cluster import KMeansCluster
from .cluster import MiniBatchKMeans
from .cluster import SpectralClustering
from .cluster import AgglomerativeClustering

from .bicluster import SpectralBiclusterer

from .decomposition import IncrementalPCA
from .decomposition import PCA

from .ensemble import IsolationForest

from .impute import SimpleImputer

from .linear_model import LinearRegression

from .neural_network import MLPClassifier

from .preprocessing import KBinsDiscretizer
from .preprocessing import MaxAbsScaler
from .preprocessing import MinMaxScaler
from .preprocessing import Normalizer
from .preprocessing import OneHotEncoder
from .preprocessing import PolynomialFeatures
from .preprocessing import PowerTransformer
from .preprocessing import QuantileTransformer
from .preprocessing import RobustScaler
from .preprocessing import StandardScaler

from .treeclassifiers import DecisionTreeClassifier


__all__ = [
    "KMeansCluster",
    "MiniBatchKMeans",
    "SpectralClustering",
    "AgglomerativeClustering",
    "SpectralBiclusterer",
    "IncrementalPCA",
    "PCA",
    "IsolationForest",
    "SimpleImputer",
    "LinearRegression",
    "MLPClassifier",
    "KBinsDiscretizer",
    "MaxAbsScaler",
    "MinMaxScaler",
    "MinMaxScaler",
    "Normalizer",
    "OneHotEncoder",
    "PolynomialFeatures",
    "PowerTransformer",
    "QuantileTransformer",
    "RobustScaler",
    "StandardScaler",
    "DecisionTreeClassifier",
]
